##############################################################################
#
# Copyright 2016 KPMG Advisory N.V. (unless otherwise stated)
#
# Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
##############################################################################
import freeipa
import os
import datetime

from resource_management import *


class FreeipaServer(Script):
    admin_login = 'admin'
    admin_password_file = '/root/admin-password'
    packages = ['ipa-server', 'bind', 'bind-dyndb-ldap']
    expected_services = ['chronyd', 'ntpd', 'ns-slapd']

    def checkport(self, number):
        """
        Certain ports must be free
        """
        import kavecommon as kc
        import time
        check = kc.check_port(number)

        if check is not None:
            if check[-2] == "TIME_WAIT":
                time.sleep(30)
                check = kc.check_port(number)

        if check is not None:
            if check[-1] is None:
                # this could be a temporary process
                time.sleep(1)
                check = kc.check_port(number)
        err = ''
        if check is not None:
            err = ("The port number %s is already in use on this machine. You must reconfigure FreeIPA ports"
                   " or install FreeIPA on a different node of your cluster. "
                   "\n\t (fd, family, type, laddr, raddr, status, pid) \n\t %s "
                   % (number, check.__str__())
                   )
            # add process info if accessible
            if check[-1] is not None:
                import psutil
                p = psutil.Process(check[-1])
                err = err + ("\n\t [user, call, status] \n\t %s"
                             % ([p.username(), p.cmdline(), p.status()].__str__())
                             )
                if p.cmdline()[0].split('/')[-1] in self.expected_services:
                    err = ''
            if len(err):
                raise OSError(err)

    def install(self, env):
        import params
        env.set_params(params)

        if params.amb_server != params.hostname:
            raise Exception('The FreeIPA server installation has a hard requirement to be installed'
                            ' on the ambari server. ambari_server: %s freeipa_server %s'
                            % (params.amb_server, params.hostname))
        import subprocess
        p0 = subprocess.Popen(["hostname", "-f"], stdout=subprocess.PIPE)
        _hostname = p0.communicate()[0].strip()
        if p0.returncode:
            raise OSError("Failed to determine hostname!")
        Package('gcc')
        Package('epel-release')
        Execute('yum clean all')
        Package('python-pip')
        Execute('pip install psutil')

        import kavecommon as kc
        tos = kc.detect_linux_version()
        # Check that all known FreeIPA ports are available
        needed_ports = [88, 123, 389, 464, 636]
        if tos.lower() in ["centos7"]:
            needed_ports = [params.pki_secure_port, params.pki_insecure_port] + needed_ports
        for port in needed_ports:
            self.checkport(port)

        self.install_packages(env)

        for package in self.packages:
            Package(package)

        # Always generate new portchanges file for automated tests
        if not os.path.exists('/etc/kave'):
            Execute('mkdir -p /etc/kave')
        Execute('python ' + os.path.dirname(__file__) + '/sed_ports.py --create /etc/kave/portchanges_new.json --debug')

        File("/etc/kave/portchanges_static.json",
             content=Template(tos.lower() + "_server.json.j2"),
             mode=0600
             )
        # Always use static file
        Execute('python ' + os.path.dirname(__file__) + '/sed_ports.py --apply /etc/kave/portchanges_static.json --debug')

        admin_password = freeipa.generate_random_password()
        Logger.sensitive_strings[admin_password] = "[PROTECTED]"

        install_command = 'ipa-server-install -U  --realm="%s" \
            --ds-password="%s" --admin-password="%s" --hostname="%s"' \
            % (params.realm, params.directory_password, admin_password, _hostname)

        # ipa-server install command. Currently --selfsign is mandatory because
        # of some anoying centos6.5 problems. The underling installer uses an
        # outdated method for the dogtag system which fails.
        # however, on centos7, this option does not exist!
        if tos.lower() in ["centos6"]:
            install_command += " --selfsign"

        if params.install_with_dns:
            if tos.lower() in ["centos7"]:
                Package("ipa-server-dns")
            install_command += ' --setup-dns --domain="%s"' % params.domain
            if params.forwarders:
                for forwarder in params.forwarders:
                    install_command += ' --forwarder="%s"' % forwarder
            else:
                install_command += ' --no-forwarders'

        # Crude check to avoid reinstalling during debugging
        if not os.path.exists(self.admin_password_file):

            # patch for long domain names!
            if params.long_domain_patch:
                Execute("grep -IlR 'Certificate Authority' /usr/lib/python*/site-packages/ipa* "
                        "| xargs sed -i 's/Certificate Authority/CA/g'")

            # This is a time-consuming command, better to log the output
            Execute(install_command, logoutput=True)
            # write password file
            File("/root/admin-password",
                 content=Template("admin-password.j2", admin_password=admin_password),
                 mode=0600
                 )
        # Ensure service is started before trying to interact with it!
        Execute('service ipa start')

        # set the default shell
        with freeipa.FreeIPA(self.admin_login, self.admin_password_file, False) as fi:
            fi.set_default_shell(params.default_shell)

        self.create_base_accounts(env)
        # create initial users and groups
        with freeipa.FreeIPA(self.admin_login, self.admin_password_file, False) as fi:

            if "Users" in params.initial_users_and_groups:
                for user in params.initial_users_and_groups["Users"]:
                    if type(user) is str or type(user) is not dict:
                        user = {"username": user}
                    username = user["username"]
                    password = None
                    if username in params.initial_user_passwords:
                        password = params.initial_user_passwords[username]
                    firstname = username
                    lastname = 'auto_generated'
                    if 'firstname' in user:
                        firstname = user['firstname']
                    if 'lastname' in user:
                        lastname = user['lastname']
                    fi.create_user_principal(identity=username, firstname=firstname,
                                             lastname=lastname, password=password)
                    if "email" in user:
                        fi.set_user_email(username, user["email"])
            if "Groups" in params.initial_users_and_groups:
                groups = params.initial_users_and_groups["Groups"]
                if type(groups) is dict:
                    groups = [{"name": gname, "members": groups[gname]} for gname in groups]
                for group in groups:
                    freeipa.create_group(group["name"])
                    for user in group["members"]:
                        fi.group_add_member(group["name"], user)
            fi.create_sudorule('allsudo', **(params.initial_sudoers))
        # create robot admin
        self.reset_robot_admin_expire_date(env)
        # if FreeIPA server is not started properly, then the clients will not install
        self.start(env)

    def conf_on_start(self, env):
        import params
        env.set_params(params)
        File("/var/kerberos/krb5kdc/kadm5.acl",
             content=InlineTemplate(params.kadm5acl_template),
             mode=0600
             )
        File("/root/createkeytabs.py",
             content=Template("createkeytabs.py", scriptpath=os.path.dirname(__file__)),
             mode=0700
             )

    def start(self, env):
        self.conf_on_start(env)
        self.distribute_robot_admin_credentials(env)
        Execute('service ipa start')

    def stop(self, env):
        Execute('service ipa stop')

    def status(self, env):
        # Pretty weird call here. We need to enforce that the keys are
        # distributed to all agents when they are first installed. This proved
        # to be tricky to achieve in Ambari. This call distributes the
        # credentials to new hosts on each status heartbeat. Pretty weird but
        # for now it serves its purpose.
        try:
            self.distribute_robot_admin_credentials(env)
        except (subprocess.CalledProcessError, OSError, TypeError, ImportError, ValueError, KeyError) as e:
            print "Failed to distribute robot credentials during status call: known exception type"
            print e, type(e)
            print sys.exc_info()
        except Exception as e:
            print "Failed to distribute robot credentials during status call: unknown exception type"
            print e, type(e)
            print sys.exc_info()

        Execute('service ipa status')

    def create_base_accounts(self, env):
        import params

        rm = freeipa.RobotAdmin()

        with freeipa.FreeIPA(self.admin_login, self.admin_password_file, False) as fi:
            # Always create the hadoop group
            fi.create_group('hadoop', 'the hadoop user group')
            fi.create_user_principal(
                rm.get_login(),
                groups=['admins'],
                password=freeipa.generate_random_password(),
                password_file=rm.get_password_file())

            # Create ldap bind user
            expiry_date = (datetime.datetime.now() + datetime.timedelta(weeks=52 * 10)).strftime('%Y%m%d%H%M%SZ')
            File("/tmp/bind_user.ldif",
                 content=Template("bind_user.ldif.j2", expiry_date=expiry_date),
                 mode=0600
                 )
            import kavecommon as kc
            _stat, _stdout, _stderr = kc.shell_call_wrapper(
                'ldapsearch -x -D "cn=directory manager" -w %s "uid=%s"'
                % (params.directory_password, params.ldap_bind_user))
            # is this user already added?
            if "dn: uid=" + params.ldap_bind_user not in _stdout:
                Execute('ldapadd -x -D "cn=directory manager" -w %s -f /tmp/bind_user.ldif'
                        % params.directory_password)
            for group in params.ldap_bind_services:
                fi.create_group(group, group + ' user group', ['--nonposix'])

    def reset_robot_admin_expire_date(self, env):
        import params
        env.set_params(params)

        rm = freeipa.RobotAdmin()
        expiry_date = (datetime.datetime.now() + datetime.timedelta(weeks=52)).strftime('%Y%m%d%H%M%SZ')
        File("/tmp/expire_date.ldif",
             content=Template("expire_date.ldif.j2",
                              login=rm.get_login(),
                              expiry_date=expiry_date),
             mode=0600
             )
        Execute('ldapadd -x -D "cn=directory manager" -w %s -f /tmp/expire_date.ldif' % params.directory_password)

    def distribute_robot_admin_credentials(self, env):
        # If this method is called during status, params will not
        # be available, and therefore I will need to read all_hosts
        # from the database instead
        # trying to import params could result in many possible issues here,
        # most commonly ImportError or KeyError
        try:
            import params
            env.set_params(params)
            all_hosts = params.all_hosts
            print "using params for all_hosts"
        except (TypeError, ImportError, ValueError, KeyError):
            all_hosts = None

        rm = freeipa.RobotAdmin()
        print "distribution to all hosts with host being", all_hosts
        rm.distribute_password(all_hosts=all_hosts)

if __name__ == "__main__":
    FreeipaServer().execute()

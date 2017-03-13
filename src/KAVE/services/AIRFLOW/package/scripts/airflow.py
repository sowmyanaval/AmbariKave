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
import os

from resource_management import *
import kavecommon as kc
from kavecommon import ApacheScript
from resource_management.core.exceptions import ComponentIsNotRunning


class Airflow(kc.ApacheScript):
    # status file is needed to know if this service was started, stores the name of the index file
    # status_file = '/etc/kave/kavelanding_started'
    airflow_config_path = "/usr/opt/local/airflow.cfg"
    airflow_webserver_pidfile_path = "/run/airflow/webserver.pid"
    systemd_env_init_path = "/etc/sysconfig/airflow"
    systemd_schd_unitfile_path = "/usr/lib/systemd/system/airflow-scheduler.service"
    systemd_ws_unitfile_path = "/usr/lib/systemd/system/airflow-webserver.service"



    def install(self, env):
        print "Installing Airflow"
        import params
        import os
        super(Airflow, self).install(env)
        kc.install_epel()

        Execute('curl "https://bootstrap.pypa.io/get-pip.py" -o "get-pip.py"')
        Execute('python get-pip.py')
        Execute('yum -y update')
        Execute('sudo yum install -y postgresql-devel python-devel mysql-devel')
        Execute('sudo yum -y install gcc gcc-c++ libffi-devel mariadb-devel cyrus-sasl-devel')
        Execute('install -U pip setuptools')
        Execute('useradd -r -s /sbin/nologin airflow')
        Execute('mkdir -p /usr/opt/local/airflow')
        Execute('chown airflow:root /usr/opt/local/airflow')
        Execute('mkdir /run/airflow')
        Execute('chown airflow:root /run/airflow')
        Execute('"echo AIRFLOW_HOME=/usr/opt/local/airflow" >> /etc/environment')

        Execute('pip install airflow')
        Execute('pip install airflow[hive]')
        #Execute('airflow | exit 0')

        self.configure(env)

    def configure(self, env):
        import params
        import os
        env.set_params(params)
        File(self.airflow_config_path,
             content=InlineTemplate(params.airflow_conf),
             mode=0755
             )
        File(self.systemd_env_init_path,
             content=Template("airflow"),
             mode=0755
             )
        File(self.systemd_schd_unitfile_path,
             content=Template("airflow-scheduler.service"),
             mode=0755
             )
        File(self.systemd_ws_unitfile_path,
             content=Template("airflow-webserver.service"),
             mode=0755
             )
        super(Airflow, self).configure(env)

        Execute('airflow initdb')

    def start(self, env):
        import params
        import os

        self.configure(env)
        Execute('systemctl start airflow-webserver')
        Execute('systemctl start airflow-scheduler')


    def stop(self, env):
        import params
        import os

        Execute('systemctl stop airflow-webserver')
        Execute('systemctl stop airflow-scheduler')

        super(Airflow, self).stop(env)

    def status(self, env):
        import params
        import os

        Execute('systemctl status airflow-webserver')
        Execute('systemctl status airflow-scheduler')

        super(Airflow, self).stop(env)


if __name__ == "__main__":
    Airflow().execute()

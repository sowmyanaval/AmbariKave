##############################################################################
#
# Copyright 2015 KPMG N.V. (unless otherwise stated)
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


class PostfixSrv(Script):
    def install(self, env):
        import params

        self.install_packages(env)
        env.set_params(params)
        self.configure(env)
        self.start(env)

    def configure(self, env):
        import params

        env.set_params(params)
        Execute('chkconfig --levels 235 postfix on')
        File('/etc/postfix/main.cf',
             content=Template("main.cf.j2"),
             mode=0644
             )
        if not os.path.isfile('/etc/postfix/main.cf'):
            raise RuntimeError("Service not installed correctly")

    def start(self, env):
        Execute('service postfix start & > /dev/null')

    def stop(self, env):
        Execute('service postfix stop & > /dev/null')

    def status(self, env):
        print "checking status..."
        print Execute('service postfix status & > /dev/null')


if __name__ == "__main__":
    PostfixSrv().execute()
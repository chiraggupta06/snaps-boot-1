# Copyright 2017 ARICENT HOLDINGS LUXEMBOURG SARL and Cable Television
# Laboratories, Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Purpose : PxeServer Provisioning
Date :21/04/2017
Created By :Yashwant Bhandari
"""
import logging
import os.path
import re
import subprocess

import os
import pkg_resources
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from snaps_boot.ansible_p.ansible_utils import ansible_playbook_launcher as apl
from snaps_boot.common.consts import consts

logger = logging.getLogger('deploy_venv')


def __main(config, operation):
    prov_dict = config.get('PROVISION')
    dhcp_dict = prov_dict.get('DHCP')
    proxy_dict = prov_dict.get('PROXY')
    pxe_dict = prov_dict.get('PXE')
    tftp_dict = prov_dict.get('TFTP')
    static_dict = prov_dict.get('STATIC')
    bmc_dict = prov_dict.get('BMC')
    subnet_list = dhcp_dict.get('subnet')
    cpu_core_dict = prov_dict.get('CPUCORE')

    if operation == "hardware":
        __pxe_server_installation(proxy_dict, pxe_dict, tftp_dict, subnet_list)
    elif operation == "boot":
        __pxe_boot(bmc_dict)
    elif operation == "bootd":
        __pxe_bootd(bmc_dict)
    elif operation == "provisionClean":
        __provision_clean()
    elif operation == "staticIPConfigure":
        __static_ip_configure(static_dict, proxy_dict)
    elif operation == "staticIPCleanup":
        __static_ip_cleanup(static_dict)
    elif operation == "setIsolCpus":
        __set_isol_cpus(cpu_core_dict)
    elif operation == "delIsolCpus":
        __del_isol_cpus(cpu_core_dict)
    else:
        print "Cannot read configuration"


def __pxe_server_installation(proxy_dict, pxe_dict, tftp_dict, subnet_list):
    """
    This will launch the shell script to  install and configure dhcp , tftp
    and apache server.
    """
    logger.info("pxe_server_installation")
    logger.info("***********************set proxy**********************")
    os.system('sh scripts/PxeInstall.sh setProxy ' + proxy_dict["http_proxy"])
    logger.info("****************installPreReq ************************")
    os.system('sh scripts/PxeInstall.sh installPreReq ' + pxe_dict["password"])
    logger.info("****************dhcpInstall***************************")
    os.system('sh scripts/PxeInstall.sh dhcpInstall ' + proxy_dict[
        "http_proxy"] + " " + pxe_dict["password"])
    logger.info("*******dhcpConfigure iscDhcpServer*********************")
    __add_isc_dhcp_file(pxe_dict, subnet_list)
    logger.info("*******dhcpConfigure generate  dhcpd.conf file***********")
    __add_dhcpd_file(subnet_list)
    __move_dhcpd_file()
    logger.info("****************dhcpRestart****************************")
    __dhcp_restart()

    logger.info("****************ftpAndApacheInstall********************")
    os.system('sh scripts/PxeInstall.sh tftpAndApacheInstall ' + proxy_dict[
        "http_proxy"] + " " + pxe_dict["password"])
    logger.info("**********tftpConfigure tftpdHpa***********************")
    os.system(
        'sh scripts/PxeInstall.sh tftpConfigure tftpdHpa' + " " + pxe_dict[
            "password"])
    logger.info("******************tftpdHpaRestart**********************")
    os.system(
        'sh scripts/PxeInstall.sh tftpdHpaRestart' + " "
        + pxe_dict["password"])
    logger.info("******************mountAndCopy************************")
    os.system('sh scripts/PxeInstall.sh mountAndCopy ' + tftp_dict["os"]
              + " " + pxe_dict["password"])
    logger.info("*************defaultFileConfigure********************")
    os.system('sh scripts/PxeInstall.sh defaultFileConfigure ' + pxe_dict[
        "serverIp"] + " " + tftp_dict["seed"] + " " + pxe_dict["password"])
    logger.info("*************bootMenuConfigure********************")
    os.system('sh scripts/PxeInstall.sh bootMenuConfigure ' + pxe_dict[
        "serverIp"] + " " + tftp_dict["seed"] + " " + pxe_dict["password"])
    logger.info("*********validateAndCreateconfigKsCfg****************")
    __create_ks_config(pxe_dict, tftp_dict, proxy_dict)
    logger.info("****************configureAnsibleFile*****************")
    __config_ansible_file()
    __config_ntp_server_file(pxe_dict)
    __restart_ntp_server(pxe_dict)


def __create_ks_config(pxe_dict, tftp_dict, proxy_dict):
    """
    used to configure ks.cfg from hosts.yaml file
    :param pxe_dict:
    :param tftp_dict:
    :param proxy_dict:
    """
    os.system('dos2unix conf/pxe_cluster/ks.cfg')
    logger.info("configuring   timezone in ks.cfg")
    __find_and_replace('conf/pxe_cluster/ks.cfg', "timezone",
                       "timezone  " + tftp_dict["timezone"])

    print " "
    logger.debug("configuring   client user password   name in ks.cfg")
    user_creds = "user " + tftp_dict["user"] + " --fullname " + tftp_dict[
        "fullname"] + " --password " + tftp_dict["password"]
    __find_and_replace('conf/pxe_cluster/ks.cfg', "user", user_creds)

    print " "
    logger.debug("configuring   client root password   name in ks.cfg")
    user_creds = "rootpw " + tftp_dict["password"]
    __find_and_replace('conf/pxe_cluster/ks.cfg', "rootpw", user_creds)

    print" "
    logger.debug("configuring server url  in ks.cfg")
    my_url = "url --url http://" + pxe_dict["serverIp"] + "/ubuntu/"
    __find_and_replace('conf/pxe_cluster/ks.cfg', "url", my_url)

    print" "
    logger.debug("configuring ntp server ip  in ks.cfg")
    ntp_server = "server " + pxe_dict["serverIp"] + " iburst"
    __find_and_replace('conf/pxe_cluster/ks.cfg', "server", ntp_server)

    print" "
    logger.debug("configuring http proxy  in ks.cfg")
    http_proxy = "Acquire::http::Proxy " + "\"" \
                 + proxy_dict["http_proxy"] + "\";"
    __find_and_replace('conf/pxe_cluster/ks.cfg', "Acquire::http::Proxy",
                       http_proxy)

    print" "
    logger.debug("configuring https proxy  in ks.cfg")
    https_proxy = "Acquire::https::Proxy " + "\"" \
                  + proxy_dict["https_proxy"] + "\";"
    __find_and_replace('conf/pxe_cluster/ks.cfg', "Acquire::https::Proxy",
                       https_proxy)

    print" "
    logger.debug("configuring ftp proxy  in ks.cfg")
    ftp_proxy = "Acquire::ftp::Proxy " + "\"" + proxy_dict["ftp_proxy"] + "\";"
    __find_and_replace('conf/pxe_cluster/ks.cfg', "Acquire::ftp::Proxy",
                       ftp_proxy)

    print" "
    logger.debug("copy local ks.cfg to location /var/www/html/ubuntu/")
    os.system('cp conf/pxe_cluster/ks.cfg /var/www/html/ubuntu/')


def __find_and_replace(fname, pat, s_after):
    """
    search a line start with pat in file fname  and replace that whole line by
    string s_after
    :param fname: filename
    :param pat: string to search a line start with
    :param s_after: string to replace the line
    :return
    """
    # first, see if the pattern is even in the file.
    # if line start with pat, then replace  whole line by subst
    with open(fname) as f:
        out_fname = fname + ".tmp"
        out = open(out_fname, "w")
        for line in f:
            if re.match(pat, line):
                logger.info("changing pattern " + pat + " --> " + s_after)
                line = s_after + "\n"
            out.write(line)
        out.close()
        os.rename(out_fname, fname)


def __config_ansible_file():
    """
    to uncomment host_key_checking field in ansible.cfg file
    """
    print" "
    logger.info("configureAnsibleFile function")
    file_path = "/etc/ansible/ansible.cfg"
    os.system('dos2unix ' + file_path)
    if os.path.exists(file_path):
        logger.info(file_path + " file exists")
        __find_and_replace(file_path, "#host_key_checking",
                           "host_key_checking = False")


def __config_ntp_server_file(pxe_dict):
    """
    to  configure   ntp.conf file
    :param pxe_dict:
    """
    print" "
    logger.info("configureNTPServerFile function")
    file_path = "/etc/ntp.conf"
    os.system('dos2unix ' + file_path)
    if os.path.exists(file_path):
        logger.info(file_path + " file exists")
        os.system('echo ' + pxe_dict[
            "password"] + ' | sudo -S cp /etc/ntp.conf /etc/ntp.conf_bkp')
        __find_and_replace(file_path, "pool 0.ubuntu.pool.ntp.org iburst",
                           "#pool 0.ubuntu.pool.ntp.org iburst")
        __find_and_replace(file_path, "pool 1.ubuntu.pool.ntp.org iburst",
                           "#pool 1.ubuntu.pool.ntp.org iburst")
        __find_and_replace(file_path, "pool 2.ubuntu.pool.ntp.org iburst",
                           "#pool 2.ubuntu.pool.ntp.org iburst")
        __find_and_replace(file_path, "pool 3.ubuntu.pool.ntp.org iburst",
                           "#pool 3.ubuntu.pool.ntp.org iburst")
        __find_and_replace(file_path, "pool ntp.ubuntu.com",
                           "#pool ntp.ubuntu.com")
        __find_and_replace(file_path, "#server 127.127.22.1",
                           "server 127.127.1.0 prefer")


def __restart_ntp_server(pxe_dict):
    """
    to restart ntp server
    :param pxe_dict
    """
    print" "
    logger.info("restartNTPServer function")
    os.system('echo ' + pxe_dict[
        "password"] + ' |  sudo -S systemctl restart  ntp.service')
    os.system('echo ' + pxe_dict[
        "password"] + ' |  sudo -S systemctl status  ntp.service')


def __add_dhcpd_file(subnet_list):
    """
    to generate local dhcpd.conf file
    """
    print" "
    logger.info("addDhcpdFile function")
    common_str = """
 ddns-update-style none;
 default-lease-time 1600;
 max-lease-time 7200;
 authoritative;
 log-facility local7;
 allow booting;
 allow bootp;
 option option-128 code 128 = string;
 option option-129 code 129 = text;
 #next-server X.X.X.X;
 filename "pxelinux.0";  """

    file_path = "conf/pxe_cluster/dhcpd.conf"
    os.system('dos2unix ' + file_path)
    if os.path.exists(file_path):
        logger.info(file_path + " file exists")
        os.system(
            'cp conf/pxe_cluster/dhcpd.conf conf/pxe_cluster/dhcpd.conf.bkp')
    with open(file_path, "w") as text_file:
        text_file.write(common_str)
        text_file.write("\n")
        for subnet in subnet_list:
            address = subnet.get('address')
            subnet_range = subnet.get('range')
            netmask = subnet.get('netmask')
            router = subnet.get('router')
            broadcast = subnet.get('broadcast-address')
            default_lease = subnet.get('default-lease')
            max_lease = subnet.get('max-lease')
            dns = subnet.get('dns')
            dn = subnet.get('dn')
            subnet_d = "subnet " + address + " netmask " + netmask \
                       + "{" + "\n" + "  range " + subnet_range + ";" + "\n" \
                       + "  option domain-name-servers " + dns + ";" + "\n" \
                       + "  option domain-name \"" + dn + "\";" + "\n" \
                       + "  option subnet-mask " + netmask + ";" + "\n" \
                       + "  option routers " + router + ";" + "\n" \
                       + "  option broadcast-address " + broadcast + ";" \
                       + "\n" + "  default-lease-time " + str(default_lease) \
                       + ";" + "\n" + "  max-lease-time " + str(max_lease) \
                       + ";" + "\n" + "  deny unknown-clients;" + "\n" + "}"
            text_file.write(subnet_d)
            text_file.write("\n")

            mac_ip_list = subnet.get('bind_host')
            for mac_ip in mac_ip_list:
                host_sub = "host ubuntu-client-" + mac_ip.get(
                    'ip') + " {" + "\n" + "  hardware ethernet " + mac_ip.get(
                    'mac') + ";" + "\n" + "  fixed-address " + mac_ip.get(
                    'ip') + ";" + "\n" + "}"
                text_file.write(host_sub)
                text_file.write("\n")


def __move_dhcpd_file():
    """
    to  move local dhcpd  file
    """
    print" "
    logger.info("moveDhcpdFile function")
    file_path_local = "conf/pxe_cluster/dhcpd.conf"
    if os.path.exists(file_path_local):
        logger.info(file_path_local + " file exists")
        if os.path.exists("/etc/dhcp/dhcpd.conf"):
            logger.info(
                '/etc/dhcp/dhcpd.conf file exists,'
                ' saving backup as dhcpd.conf.bkp')
            os.system('cp /etc/dhcp/dhcpd.conf /etc/dhcp/dhcpd.conf.bkp')
        logger.info("replacing file /etc/dhcp/dhcpd.conf ")
        os.system('cp conf/pxe_cluster/dhcpd.conf /etc/dhcp/')


def __add_isc_dhcp_file(pxe_dict, subnet_list):
    """
    to  add interfaces in isc-dhcp-server  file
    """
    print" "
    logger.info("addIscDhcpFile function")

    file_path = "conf/pxe_cluster/isc-dhcp-server"
    os.system('dos2unix ' + file_path)
    if os.path.exists(file_path):
        logger.info(file_path + " file exists")
        all_interface = ""

        for subnet in subnet_list:
            listen_iface = subnet.get('listen_iface')
            all_interface = all_interface + " " + str(listen_iface)

        all_interface = all_interface.strip()
        print all_interface
        __find_and_replace(file_path, "INTERFACES",
                           "INTERFACES=" + "\"" + all_interface + "\"")
        if os.path.exists("/etc/default/isc-dhcp-server"):
            logger.info("/etc/default/isc-dhcp-server  file exists")
            os.system(
                'echo ' + pxe_dict["password"]
                + ' |  sudo -S cp /etc/default/isc-dhcp-server /etc/default'
                  '/isc-dhcp-server.bkp')
            logger.info("saving backup as /etc/default/isc-dhcp-server.bkp")
        os.system(
            'echo ' + pxe_dict["password"]
            + ' |  sudo -S cp conf/pxe_cluster/isc-dhcp-server /etc/default/')


def __dhcp_restart():
    """
    to  restart dhcp server
    """
    print" "
    logger.info("dhcpRestart function")
    os.system(' systemctl restart  isc-dhcp-server')
    os.system(' systemctl status  isc-dhcp-server')


def __ipmi_power_status(bmc_ip, bmc_user, bmc_pass):
    """
    to  get the status of bmc
    """
    print" "
    logger.info("ipmiPowerStatus function")
    print bmc_ip
    print bmc_user
    print bmc_pass
    os.system(
        'ipmitool -I lanplus -H ' + bmc_ip + ' -U ' + bmc_user + '  -P '
        + bmc_pass + '  chassis power status')


def __ipmi_lan_status(bmc_ip, bmc_user, bmc_pass):
    """
    to  get the status of lan
    """
    print" "
    logger.info("ipmiLanStatus function")
    os.system(
        'ipmitool -I lanplus -H ' + bmc_ip + ' -U ' + bmc_user + '  -P '
        + bmc_pass + '  lan print 1')


def __ipmi_set_boot_order_pxe(bmc_ip, bmc_user, bmc_pass, order):
    """
    to set the boot order pxe
    """
    print" "
    logger.info("ipmiSetBootOrderPxe function")
    os.system(
        'ipmitool -I lanplus -H ' + bmc_ip + ' -U ' + bmc_user + '  -P '
        + bmc_pass + '  chassis bootdev ' + order)


def __ipmi_reboot_system(bmc_ip, bmc_user, bmc_pass):
    """
    to reboot the system via ipmi
    """
    print" "
    logger.info("ipmiRebootSystem function")
    os.system(
        'ipmitool -I lanplus -H ' + bmc_ip + ' -U ' + bmc_user + '  -P '
        + bmc_pass + '  chassis power cycle')


def __ipmi_power_on_system(bmc_ip, bmc_user, bmc_pass):
    """
    to power on the system via ipmi
    """
    print" "
    logger.info("ipmiPowerOnSystem function")
    os.system(
        'ipmitool -I lanplus -H ' + bmc_ip + ' -U ' + bmc_user + '  -P '
        + bmc_pass + '  chassis power on')


def __ipmi_power_off_system(bmc_ip, bmc_user, bmc_pass):
    """
    to power off the system via ipmi
    """
    print" "
    logger.info("ipmiPowerOnSystem function")
    os.system(
        'ipmitool -I lanplus -H ' + bmc_ip + ' -U ' + bmc_user + '  -P '
        + bmc_pass + '  chassis power off')


def __pxe_boot(bmc_dict):
    """
    to start boot via ipmi
    """
    print" "
    logger.info("pxeBoot function")
    for host in bmc_dict.get('host'):
        user = host.get('user')
        password = host.get('password')
        ip = host.get('ip')
        __ipmi_power_status(ip, user, password)
        __ipmi_set_boot_order_pxe(ip, user, password, "pxe")
        __ipmi_reboot_system(ip, user, password)


def __pxe_bootd(bmc_dict):
    """
    to start boot  via disk
    """
    print" "
    logger.info("pxeBoot function")
    for host in bmc_dict.get('host'):
        user = host.get('user')
        password = host.get('password')
        ip = host.get('ip')
        __ipmi_power_status(ip, user, password)
        __ipmi_set_boot_order_pxe(ip, user, password, "disk")
        __ipmi_reboot_system(ip, user, password)


def __provision_clean():
    """
    to clean the pxe server installation
    """
    print" "
    logger.info("provisionClean function")
    logger.info("stop isc-dhcp-server::systemctl stop isc-dhcp-server")
    os.system('systemctl stop isc-dhcp-server')
    logger.info("stop tftpd-hpa::systemctl stop tftpd-hpa")
    os.system('systemctl stop tftpd-hpa')
    os.system('rm -rf /var/lib/tftpboot/*')
    logger.info("removing tftpd")
    os.system('apt-get  -y remove tftpd-hpa ')
    os.system('apt-get  -y remove inetutils-inetd')
    logger.info("stop apache2::systemctl stop apache2")
    os.system('systemctl stop apache2')
    os.system('rm -rf /var/www/html/ubuntu')
    logger.info("removing apache2")
    os.system('apt-get  -y remove apache2')

    logger.info("removing dhcpServer")
    os.system('apt-get  -y remove isc-dhcp-server')
    logger.info("unmount mount point")
    os.system('umount  /mnt')


def __static_ip_configure(static_dict, proxy_dict):
    playbook_path = pkg_resources.resource_filename(
        'snaps_boot.ansible_p.commission.hardware.playbooks',
        'setIPConfig.yaml')
    playbook_path_bak = pkg_resources.resource_filename(
        'snaps_boot.ansible_p.commission.hardware.playbooks',
        'interfaceBak.yaml')

    host = static_dict.get('host')
    print "HOSTS---------------"
    print host
    valid = __validate_static_config(static_dict)
    if valid is False:
        logger.info(
            "Configuration error please define IP for all the interface types")
        exit()
    http_proxy = proxy_dict.get('http_proxy')
    https_proxy = proxy_dict.get('https_proxy')
    print host[0]
    iplist = []
    next_word = None
    with open("conf/pxe_cluster/ks.cfg") as openfile:
        for line in openfile:
            list_word = line.split()
            for part in line.split():
                if "rootpw" in part:
                    next_word = list_word[list_word.index("rootpw") + 1]

    user_name = 'root'
    password = next_word
    check_dir = os.path.isdir(consts.SSH_PATH)
    if not check_dir:
        os.makedirs(consts.SSH_PATH)
    for i in range(len(host)):
        target = host[i].get('access_ip')
        iplist.append(target)
    consts.KEY_IP_LIST = iplist
    for i in range(len(host)):
        target = host[i].get('access_ip')
        __create_and_save_keys()

        command = 'sshpass -p \'%s\' ssh-copy-id -o ' \
                  'StrictHostKeyChecking=no %s@%s' \
                  % (password, user_name, target)

        logger.info('Issuing following command - %s', command)
        retval = subprocess.call(command, shell=True)

        if retval != 0:
            raise Exception('System command failed - ' + command)

        interfaces = host[i].get('interfaces')
        backup_var = "Y"
        apl.__launch_ansible_playbook(
            iplist, playbook_path_bak, {'target': target, 'bak': backup_var})

        # TODO/FIXME - why is the var 'i' being used in both the inner and
        # outer loops???
        for i in range(len(interfaces)):
            address = interfaces[i].get('address')
            gateway = interfaces[i].get('gateway')
            netmask = interfaces[i].get('netmask')
            iface = interfaces[i].get('iface')
            dns = interfaces[i].get('dns')
            dn = interfaces[i].get('dn')
            intf_type = interfaces[i].get('type')
            apl.__launch_ansible_playbook(
                iplist, playbook_path, {
                    'target': target,
                    'address': address,
                    'gateway': gateway,
                    'netmask': netmask,
                    'iface': iface,
                    'http_proxy': http_proxy,
                    'https_proxy': https_proxy,
                    'type': intf_type,
                    'dns': dns,
                    'dn': dn})


def __create_and_save_keys():

    keys = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537,
        key_size=2048)

    # Save Keys if not already exist
    priv_key_path = os.path.expanduser('~/.ssh/id_rsa')
    priv_key_file = None
    if not os.path.isfile(priv_key_path):
        # Save the keys
        ssh_dir = os.path.expanduser('~/.ssh')
        if not os.path.isdir(ssh_dir):
            os.mkdir(ssh_dir)

        # Save Private Key
        try:
            priv_key_file = open(priv_key_path, 'wb')
            priv_key_file.write(keys.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()))
            os.chmod(priv_key_path, 0o400)
        except:
            raise
        finally:
            if priv_key_file:
                priv_key_file.close()

    pub_key_path = os.path.expanduser('~/.ssh/id_rsa.pub')
    pub_key_file = None
    if not os.path.isfile(pub_key_path):
        # Save the keys
        ssh_dir = os.path.expanduser('~/.ssh')
        if not os.path.isdir(ssh_dir):
            os.mkdir(ssh_dir)

        # Save Public Key
        try:
            pub_key_file = open(pub_key_path, 'wb')
            pub_key_file.write(keys.public_key().public_bytes(
                serialization.Encoding.OpenSSH,
                serialization.PublicFormat.OpenSSH))
            os.chmod(pub_key_path, 0o400)
        except:
            raise
        finally:
            if pub_key_file:
                pub_key_file.close()


def __static_ip_cleanup(static_dict):
    playbook_path = pkg_resources.resource_filename(
        'snaps_boot.ansible_p.commission.hardware.playbooks',
        'delIPConfig.yaml')
    playbook_path_bak = pkg_resources.resource_filename(
        'snaps_boot.ansible_p.commission.hardware.playbooks',
        'interfaceBak.yaml')

    host = static_dict.get('host')
    iplist = []
    next_word = None
    with open("conf/pxe_cluster/ks.cfg") as openfile:
        for line in openfile:
            list_word = line.split()
            for part in line.split():
                if "rootpw" in part:
                    next_word = list_word[list_word.index("rootpw") + 1]

    user_name = 'root'
    password = next_word
    check_dir = os.path.isdir(consts.SSH_PATH)
    if not check_dir:
        os.makedirs(consts.SSH_PATH)
    for i in range(len(host)):
        target = host[i].get('access_ip')
        iplist.append(target)
    print iplist
    for i in range(len(host)):
        target = host[i].get('access_ip')
        subprocess.call(
            'echo -e y|ssh-keygen -b 2048 -t rsa -f '
            '/root/.ssh/id_rsa -q -N ""',
            shell=True)
        command = 'sshpass -p %s ssh-copy-id -o ' \
                  'StrictHostKeyChecking=no %s@%s' \
                  % (password, user_name, target)
        subprocess.call(command, shell=True)
        interfaces = host[i].get('interfaces')
        backup_var = "N"
        apl.__launch_ansible_playbook(
            iplist, playbook_path_bak, {'target': target, 'bak': backup_var})

        # TODO/FIXME - why is the var 'i' being used in both the inner and
        # outer loops???
        for i in range(len(interfaces)):
            address = interfaces[i].get('address')
            gateway = interfaces[i].get('gateway')
            netmask = interfaces[i].get('netmask')
            iface = interfaces[i].get('iface')
            dns = interfaces[i].get('dns')
            dn = interfaces[i].get('dn')
            intf_type = interfaces[i].get('type')
            apl.__launch_ansible_playbook(
                iplist, playbook_path, {
                    'target': target,
                    'address': address,
                    'gateway': gateway,
                    'netmask': netmask,
                    'iface': iface,
                    'type': intf_type,
                    'dns': dns,
                    'dn': dn})


def __validate_static_config(static_dict):
    hosts = static_dict.get('host')
    valid = True
    for host in hosts:
        interfaces = host.get('interfaces')
        for interface in interfaces:
            if interface.get('type') == 'data' and interface.get(
                    'address') == "":
                valid = False
            if interface.get('type') == 'tenant' and interface.get(
                    'address') == "":
                valid = False
            if interface.get('type') == 'management' and interface.get(
                    'address') == "":
                valid = False
    return valid


def __set_isol_cpus(cpu_core_dict):
    """
    to   set isolate cpu  in /etc/default/grub file
    """
    logger.info("setIsolCpus function")
    iplist = []
    root_pass = None
    with open("conf/pxe_cluster/ks.cfg") as openfile:
        for line in openfile:
            list_word = line.split()
            for part in line.split():
                if "rootpw" in part:
                    root_pass = list_word[list_word.index("rootpw") + 1]
    user_name = 'root'
    playbook_path = pkg_resources.resource_filename(
        'snaps_boot.ansible_p.commission.hardware.playbooks',
        'setIsolCpus.yaml')
    host = cpu_core_dict.get('host')
    for ipCpu1 in host:
        target1 = ipCpu1.get('ip')
        iplist.append(target1)

    for ipCpu in host:
        target = ipCpu.get('ip')
        isolcpus = ipCpu.get('isolcpus')
        hugepagesz = ipCpu.get('hugepagesz')
        hugepages = ipCpu.get('hugepages')
        if isolcpus:
            logger.info("isolate cpu's for " + target + " are " + isolcpus)
            logger.info("hugepagesz for " + target + "  " + hugepagesz)
            logger.info("hugepages for " + target + "  " + hugepages)
            subprocess.call(
                'echo -e y|ssh-keygen -b 2048 -t rsa -f '
                '/root/.ssh/id_rsa -q -N ""',
                shell=True)
            command = 'sshpass -p %s ssh-copy-id -o ' \
                      'StrictHostKeyChecking=no %s@%s' % (
                          root_pass, user_name, target)
            subprocess.call(command, shell=True)
            apl.__launch_ansible_playbook(
                iplist, playbook_path, {
                    'target': target,
                    'isolcpus': isolcpus,
                    'hugepagesz': hugepagesz,
                    'hugepages': hugepages})


def __del_isol_cpus(cpu_core_dict):
    """
    to set isolate cpu  in /etc/default/grub file
    """
    logger.info("setIsolCpus function")
    iplist = []
    root_pass = None
    with open("conf/pxe_cluster/ks.cfg") as openfile:
        for line in openfile:
            list_word = line.split()
            for part in line.split():
                if "rootpw" in part:
                    root_pass = list_word[list_word.index("rootpw") + 1]
    user_name = 'root'
    playbook_path = pkg_resources.resource_filename(
        'snaps_boot.ansible_p.commission.hardware.playbooks',
        'delIsolCpus.yaml')
    host = cpu_core_dict.get('host')
    for ipCpu1 in host:
        target1 = ipCpu1.get('ip')
        iplist.append(target1)

    for ipCpu in host:
        target = ipCpu.get('ip')
        isolcpus = ipCpu.get('isolcpus')
        hugepagesz = ipCpu.get('hugepagesz')
        hugepages = ipCpu.get('hugepages')
        if isolcpus:
            logger.info("isolate cpu's for " + target + " are " + isolcpus)
            logger.info("hugepagesz for " + target + "  " + hugepagesz)
            logger.info("hugepages for " + target + "  " + hugepages)
            subprocess.call(
                'echo -e y|ssh-keygen -b 2048 -t rsa -f '
                '/root/.ssh/id_rsa -q -N ""',
                shell=True)
            command = 'sshpass -p %s ssh-copy-id -o ' \
                      'StrictHostKeyChecking=no %s@%s' \
                      % (root_pass, user_name, target)
            subprocess.call(command, shell=True)
            apl.__launch_ansible_playbook(
                iplist, playbook_path, {
                    'target': target,
                    'isolcpus': isolcpus,
                    'hugepagesz': hugepagesz,
                    'hugepages': hugepages})

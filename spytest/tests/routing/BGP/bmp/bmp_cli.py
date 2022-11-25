
# -*- coding:utf-8 -*-
import pytest
from spytest import st, tgapi, SpyTestDict
import time
import json
import re
import threading
import os
import psutil
import subprocess

ALICLI_VIEW = "cli"
CONFIG_VIEW = "configure terminal"
ROUTE_BGP_VIEW = "router bgp {}"

# bmp targets WORD
BMP_TARGET = "{} bmp targets {}"
# bmp connect HOSTNAME port <1-65535> min-retry <100-86400000> max-retry <100-86400000>
BMP_CONNECT = "{} bmp connect {} port {}  min-retry {} max-retry {}"
# bmp connect HOSTNAME port <1-65535> vrf WORD min-retry <100-86400000> max-retry <100-86400000>
BMP_CONNECT_VRF = "{} bmp connect {} port {} vrf {} min-retry {} max-retry {}"
# bmp monitor (ipv4|ipv6) unicast adj-in (pre-policy|post-policy)
BMP_MONITOR = "{} bmp monitor {} unicast adj-in {}"
# bmp update-source (A.B.C.D|X:X::X:X)
# no bmp update-source
BMP_UPDATE_SOURCE = "{} bmp update-source {}"

class BMP_INS():
    
    kafka_file_pid = ''
    kafka_proc_dict = {}

    file_mapping = {
        'openbmp.parsed.collector':'kafka_collector',
        'openbmp.parsed.router':'kafka_router',
        'openbmp.parsed.peer':'kafka_peer',
        'openbmp.parsed.base_attribute':'kafka_baseattr',
        'openbmp.parsed.unicast_prefix':'kafka_unicast_prefix',
        'openbmp.parsed.l3vpn':'kafka_l3vpn',
        'openbmp.parsed.evpn':'kafka_evpn',
        'openbmp.parsed.ls_node':'kafka_lsnode',
        'openbmp.parsed.ls_link':'kafka_lslink',
        'openbmp.parsed.ls_prefix':'kafka_lsprefix',
        'openbmp.parsed.bmp_stat':'kafka_bmpstat',
        'openbmp.bmp_raw':'kafka_bmp_raw'
    }   

    def __init__(self, dut, test_data, param_data, bgp_ins):
        self.data = test_data
        self.param_data = param_data

        self.dut = dut
        # router bgp 100  /  router bgp 200 vrf 10
        self.bgp_ins =  ROUTE_BGP_VIEW.format(bgp_ins)
        
    
    def config_bmp_target(self, target_group_name, iscreate = True):
        bmp_cli = BMP_TARGET.format('' if iscreate else 'no', target_group_name)
        command =  "{} -c '{}'-c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.bgp_ins, bmp_cli)
        st.config(self.dut, command)
        self.bmp_view = 'bmp targets {}'.format(target_group_name)

    def config_bmp_connect(self, bmpserver_host, bmpserver_port, min_r, max_r, iscreate = True):
        bmp_cli = BMP_CONNECT.format('' if iscreate else 'no', bmpserver_host, bmpserver_port, min_r, max_r)
        command =  "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.bgp_ins, self.bmp_view, bmp_cli)
        st.config(self.dut, command)

    def config_bmp_connect_vrf(self, bmpserver_host, bmpserver_port, vrf, min_r, max_r, iscreate = True):
        bmp_cli = BMP_CONNECT_VRF.format('' if iscreate else 'no', bmpserver_host, bmpserver_port, vrf, min_r, max_r)
        command =  "{}  -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.bgp_ins, self.bmp_view, bmp_cli)
        st.config(self.dut, command)

    def config_bmp_monitor(self, ip_type, policy, iscreate = True):
        bmp_cli = BMP_MONITOR.format('' if iscreate else 'no', ip_type, policy)
        command =  "{}  -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.bgp_ins, self.bmp_view, bmp_cli)
        st.config(self.dut, command)

    def config_bmp_source_update(self, source, iscreate = True):
        bmp_cli = BMP_UPDATE_SOURCE.format('' if iscreate else 'no', source)
        command =  "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.bgp_ins, self.bmp_view, bmp_cli)
        st.config(self.dut, command)

    def show_bmp(self):
        # bmp_cli = 'show bmp'
        # cmd = "{} -c '{}'".format(ALICLI_VIEW, bmp_cli)
        # output = st.show(self.dut, cmd)
        out = st.show(self.dut, "show bmp", type='vtysh')
        st.log("===============show bmp================")
        st.log(out)
        return out

    def parse_show_bmp(self, vrf='default'):
        output = self.show_bmp()
        bmp_map = {}
        bmp_map['targets'] = []
        check_var = vrf
        current_target = ''
        for i in range(len(output)):
            if not bmp_map.has_key('vrf'):
                if output[i].get('vrf_name') != "":
                    if output[i].get('vrf_name') == check_var:
                        bmp_map['vrf'] = check_var
                        continue
            else:
                if output[i].get('targets') != "":
                    target = {'targets_name' : output[i].get('targets'),
                        'mirrot_enable' : output[i].get('mirrot_enable'),
                        'conn_clients' : output[i].get('conn_clients'),
                        'clients':[]
                    }
                    bmp_map['targets'].append(target)
                    if int(target['conn_clients']) > 0:
                        current_target = target['targets_name']
                        st.log("current_target = {}".format(current_target))
                
                if output[i].get('remote') != "":
                    if current_target != '':
                        client = {
                            'remote':output[i].get('remote'),
                            'uptime':output[i].get('uptime'),
                            'monsent':output[i].get('monsent'),
                            'mirrsent':output[i].get('mirrsent'),
                            'mirrlost':output[i].get('mirrlost'),
                            'bytesent':output[i].get('bytesent'),
                            'byteq':output[i].get('byteq'),
                            'byteqkernel':output[i].get('byteqkernel')
                            }
                        for t in bmp_map['targets']:
                            if t['targets_name'] == current_target:
                                t['clients'].append(client)
        return bmp_map
    
    def check_key_point(self, pattern):
        pass        

    def save_config_and_reboot(self):
        cmd = "{} -c '{}' -c 'copy running-config startup-config'".format(ALICLI_VIEW, CONFIG_VIEW)
        st.config(self.dut, cmd)
        st.wait(1)
        st.log("start reboot")
        st.reboot(self.dut)
        st.wait(5)
        st.log("finish reboot")

    def show_frr_running_config_json(self):
        cmd = "vtysh -c 'show running-config json'"
        output = st.show(self.dut, cmd, skip_tmpl=True)

        st.log("===================")
        json_str = json.dumps(output).encode('utf-8')
        json_str = json_str[:json_str.rfind('end')].replace('true','"true"').replace("\\n","").replace("\\","").strip('"')
        output_json = json.loads(json_str)

        st.log(output_json)
        st.log("===================")
        return output_json

    @staticmethod
    def bmp_server_data_read(topic):
        file_prefix = "/var/spytest/"
   
        file_name = BMP_INS.file_mapping.get(topic)
        #tail_cmd = 'ls /var/spytest/'
        # tail_cmd = 'nohup tail -f {} &> {}_tail.log & echo $! > run.pid'.format(file_prefix+file_name, file_name)
        # pid = os.system(tail_cmd)
        # st.log("cmd:{} -- pid = {}".format(tail_cmd, pid))
        # BMP_INS.kafka_file_pid = pid
        clear_cmd = ": > {} ".format(file_prefix+file_name)
        os.system(clear_cmd)
        #proc = subprocess.Popen(['tail', '-f', file_prefix+file_name, '>' , file_prefix+file_name+'_tail.log &'], shell=True)
        #st.log("pid = {}".format(proc.pid))
        #BMP_INS.kafka_proc_dict['topic'] = proc


    @staticmethod
    def close_bmp_kafka_file(topic):
        if BMP_INS.kafka_proc_dict.has_key(topic):
            st.log("terminate pid = {}".format(BMP_INS.kafka_proc_dict['topic'].pid))
            BMP_INS.kafka_proc_dict['topic'].terminate()

    @staticmethod
    def read_bmp_data(topic):
        file_prefix = "/var/spytest/"
        file_name = BMP_INS.file_mapping.get(topic)
        file_log_name = file_prefix+file_name
        #cmd = 'cat {}'.format(file_log_name)
        #output = os.popen(cmd).readlines()
        # parse content
        msg_list = []
        with open(file_log_name) as f: 
            line = f.readline()
            while line:
                msg = {}
                # st.log("topic: {}, data:{}".format(topic, line))
                if line.startswith('action'):
                    items = line.split(" -- ")
                    for it in items:
                        kv = it.split(':',1)
                        if len(kv) == 2:
                            if kv[1] == '\n':
                                kv[1] = ''
                            msg[kv[0]] = kv[1]
                        elif len(kv) == 1:
                            msg[kv[0]] = ""

                    # st.log("topic: {}, processed msg:{}".format(topic, msg))
                    msg_list.append(msg)
                line = f.readline()

        # st.log(msg_list)
        return msg_list
    
    @staticmethod
    def match_bmp_msg(topic, action, key, value):
        msg_list = BMP_INS.read_bmp_data(topic)

        for msg in msg_list:
            match_action = False
            match_kv = False            

            if msg.has_key('action'):
                if msg['action'] == action:
                    match_action = True

            if msg.has_key(key):
                if msg[key] == value:
                    match_kv = True

            st.log("match_action = {} , match_kv = {} ".format(match_action, match_kv))
            if match_action and match_kv:
                return True
        return False
from spytest.dicts import SpyTestDict

data = SpyTestDict()

data.ecmp_503_504_dut1_dut2_portlist = ['Ethernet2', 'Ethernet4', 'Ethernet50', 'Ethernet51', 'Ethernet52', 'Ethernet53']
data.ecmp_503_504_dut_tg_portlist = ['Ethernet33', 'Ethernet34']
data.ecmp_501_502_dut1_dut2_portlist = ['Ethernet54', 'Ethernet53']
data.ecmp_501_502_dut_RJ_portlist = ['Ethernet5', 'Ethernet6', 'Ethernet21', 'Ethernet22']
data.ecmp_501_502_dut_tg_portlist = ['Ethernet35', 'Ethernet36']
data.ecmp_501_502_dut_RJ_portlist2 = ['Ethernet5', 'Ethernet6']
data.dut_ecmp_scale_start_subintf = '201'
data.dut_ecmp_scale_subintf_num = 13
data.dut_isolate_group_num = 6
data.dut_bfd_port_list = ['Ethernet3']
data.dut1_vrf1_ip_addr = ["12.109.104.2", "12.110.104.2", "12.111.100.2", " 12.112.100.2"]
data.dut1_vrf1_ipv6_addr = ["fd40:12:109:104::2", "fd40:12:110:104::2", "fd40:12:111:100::2", "fd40:12:112:100::2"]
data.dut1_vrf1_id = ["503", "503", "501", "501"]
data.dut1_vrf2_ip_addr = ["12.109.106.2", "12.110.106.2", "12.111.102.2", "12.112.102.2"]
data.dut1_vrf2_ipv6_addr = ["fd40:12:109:106::2", "fd40:12:110:106::2", "fd40:12:111:102::2", "fd40:12:112:102::2"]
data.dut1_vrf2_id = ["504", "504", "502", "502"]
data.dut_traffic_vrf_name = {"501": "long-vrf-501", "502": "long-vrf-502", 
                            "503": "long-vrf-503", "504": "long-vrf-504"}
data.dut_tg_bfd_vrf_name = {"TG1_1":"long-vrf-TG-bfd1", "TG1_2":"long-vrf-TG-bfd2",
                            "TG1_3":"long-vrf-TG-bfd3", "TG1_4":"long-vrf-TG-bfd4"}
data.dut1_dut2_bfd_vrf_name = ["long-vrf-dut-bfd1"]

data.dut2_vrf1_ip_addr = ["11.109.104.1", "11.110.104.1"]
data.dut2_vrf1_ipv6_addr = ["fd40:11:109:104::1", "fd40:11:110:104::1"]
data.dut2_vrf1_id = ["503", "503"]
data.dut2_vrf2_ip_addr = ["11.109.106.1", "11.110.106.1"]
data.dut2_vrf2_ipv6_addr = ["fd40:11:109:106::1", "fd40:11:110:106::1"]
data.dut2_vrf2_id = ["504", "504"]

data.dut3_vrf1_ip_addr = ["11.61.100.1", "11.62.100.1"]
data.dut3_vrf1_id = ["501", "501"]
data.dut3_vrf2_ip_addr = ["11.61.102.1", "11.62.102.1"]
data.dut3_vrf2_id = ["502", "502"]

data.dut1_bfdv4_start_ip_addr = ["109.1.0.1","110.2.0.1","111.3.0.1", "112.4.0.1"]
data.dut1_bfdv6_start_ip_addr = ["109:1::1","110:2::1","111:3::1", "112:4::1"]
data.dut2_bfdv4_start_ip_addr = ["109.1.0.1","110.2.0.1"]
data.dut2_bfdv6_start_ip_addr = ["109:1::1","110:2::1"]
data.tg1_bfdv4_start_ip_addr = ["109.1.0.2","110.2.0.2","111.3.0.2", "112.4.0.2"]
data.tg1_bfdv6_start_ip_addr = ["109:1::2","110:2::2","111:3::2", "112:4::2"]
data.tg2_bfdv4_start_ip_addr = ["109.1.0.2","110.2.0.2"]
data.tg2_bfdv6_start_ip_addr = ["109:1::2","110:2::2"]

data.tg1_vrf1_ip_addr = ["12.109.104.1", "12.110.104.1", "12.111.100.1", "12.112.100.1"]
data.tg1_vrf1_ipv6_addr = ["fd40:12:109:104::1", "fd40:12:110:104::1", "fd40:12:111:100::1", "fd40:12:112:100::1"]
data.tg1_vrf2_ip_addr = ["12.109.106.1", "12.110.106.1", "12.111.102.1", "12.112.102.1"]
data.tg1_vrf2_ipv6_addr = ["fd40:12:109:106::1", "fd40:12:110:106::1", "fd40:12:111:102::1", "fd40:12:112:102::1"]
data.tg1_vrf1_router_prefix_list = ["202.1.0.0", "202.1.0.0", "204.1.0.0", "204.1.0.0"]
data.tg1_vrf1_router_v6_prefix_list = ["3000:1::1", "3000:1::1", "3000:2::1", "3000:2::1"]
data.tg1_vrf2_router_prefix_list = ["202.2.0.0", "202.2.0.0", "204.2.0.0", "204.2.0.0"]
data.tg1_vrf2_router_v6_prefix_list = ["3001:1::1", "3001:1::1", "3001:1::1", "3001:1::1"]
data.tg1_vrf1_router_count_list = ["70000","70000","50000","50000"]
data.tg1_vrf1_router_v6_count_list = ['50000', '50000','50000','50000']
data.tg1_vrf2_router_count_list = ["70000","70000","50000", "50000"]
data.tg1_vrf2_router_v6_count_list = ['50000', '50000','50000','50000']
data.tg1_router_prefix_length = "31"
data.tg1_router_v6_prefix_length = "64"

data.tg2_vrf1_ip_addr = ["11.109.104.2", "11.110.104.2"]
data.tg2_vrf1_ipv6_addr = ["fd40:11:109:104::2", "fd40:11:110:104::2"]
data.tg2_vrf2_ip_addr = ["11.109.106.2", "11.110.106.2"]
data.tg2_vrf2_ipv6_addr = ["fd40:11:109:106::2", "fd40:11:110:106::2"]
data.tg2_vrf1_router_prefix = "200.1.0.0"
data.tg2_vrf1_router_v6_prefix = "4000:1::1"
data.tg2_vrf2_router_prefix = "200.2.0.0"
data.tg2_vrf2_router_v6_prefix = "4001:1::1"
data.tg2_router_prefix_length = "32"
data.tg2_router_v6_prefix_length = "64"
data.tg2_router_count = "10000"

data.tg3_vrf1_ip_addr = ["11.61.100.2", "11.62.100.2"]
data.tg3_vrf2_ip_addr = ["11.61.102.2", "11.62.102.2"]
data.tg3_vrf1_router_prefix = "206.1.0.0"
data.tg3_vrf2_router_prefix = "206.2.0.0"
data.tg3_router_prefix_length = "32"
data.tg3_router_count = "10000"

data.tg1_vrf_bgp_as = "4200015158"
data.tg2_vrf_bgp_as = "4200015156"
data.tg3_vrf_bgp_as = "4200015159"
data.dut1_vrf_bgp_as = "4200015155"
data.dut2_vrf_bgp_as = "4200015154"
data.dut3_vrf_bgp_as = "4200015157"

data.dut2_v4_start_ip_addr = ["109.1.0.1","110.2.0.1"]
data.dut2_v6_start_ip_addr = ["109:1::1","110:2::1"]
data.tg2_v4_start_ip_addr = ["109.1.0.2","110.2.0.2"]
data.tg2_v6_start_ip_addr = ["109:1::2","110:2::2"]

data.dut_bfd_timer = "300"
data.tg_bfd_timer = "300"
# data.traffic_rate_precent = "99.9"
data.traffic_rate_precent = "50"
data.ruijie_traffic_rate_precent = "40.0"
data.tg_list = []
data.tg_ph_list = []
data.tg1_handle = [0,0,0,0]
data.tg2_handle = [0,0]
data.tg3_handle = [0,0]
data.streams = {}

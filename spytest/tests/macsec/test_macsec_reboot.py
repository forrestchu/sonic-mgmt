import pytest
import re

from spytest import st, tgapi, SpyTestDict
import apis.routing.ip as ipfeature
import apis.macsec.macsec as macsec_api
import apis.system.reboot as reboot

data = SpyTestDict()
data.profile_name = "GCM-128"
data.cipher_suite = "GCM-AES-128"
data.primary_ckn = "3007"
data.primary_cak = "00112233445566778899001122334455"

data.ip4_addr = ["188.188.1.1", "188.188.1.2"]
data.ip6_addr = ["188::1", "188::2"]
data.af_ipv4 = "ipv4"
data.af_ipv6 = "ipv6"
data.interfaces = []

@pytest.fixture(scope="module", autouse=True)
def macsec_module_hooks(request):
    global vars
    vars = st.ensure_min_topology("D1D2:1")

    ipfeature.config_ip_addr_interface(vars.D1, vars.D1D2P1, data.ip4_addr[0], 24, family=data.af_ipv4)
    ipfeature.config_ip_addr_interface(vars.D2, vars.D2D1P1, data.ip4_addr[1], 24, family=data.af_ipv4)
    ipfeature.config_ip_addr_interface(vars.D1, vars.D1D2P1, data.ip6_addr[0], 96, family=data.af_ipv6)
    ipfeature.config_ip_addr_interface(vars.D2, vars.D2D1P1, data.ip6_addr[1], 96, family=data.af_ipv6)

    yield

    ipfeature.delete_ip_interface(vars.D1, vars.D1D2P1, data.ip4_addr[0], 24, family=data.af_ipv4)
    ipfeature.delete_ip_interface(vars.D2, vars.D2D1P1, data.ip4_addr[1], 24, family=data.af_ipv4)
    ipfeature.delete_ip_interface(vars.D1, vars.D1D2P1, data.ip6_addr[0], 96, family=data.af_ipv6)
    ipfeature.delete_ip_interface(vars.D2, vars.D2D1P1, data.ip6_addr[1], 96, family=data.af_ipv6)

@pytest.fixture(scope="function", autouse=True)
def macsec_func_hooks(request):
    # Function configuration
    yield
    # Function cleanup

    # cleanup DUT1
    # disable all macsec port
    for interface in data.interfaces:
        macsec_api.disable_macsec_port(vars.D1, interface)

    # delete profile
    macsec_api.delete_macsec_profile(vars.D1, data.profile_name)

    # cleanup DUT2
    macsec_api.disable_macsec_port(vars.D2, vars.D2D1P1)
    macsec_api.delete_macsec_profile(vars.D2, data.profile_name)

def check_ping():
    # D1 ping D2
    if not ipfeature.ping_poll(vars.D1, data.ip4_addr[1], family="ipv4", iter=3, count="4"):
        st.error("D1 ping {} failed".format(data.ip4_addr[1]))
        return False
    if not ipfeature.ping_poll(vars.D1, data.ip6_addr[1], family="ipv6", iter=3, count="4"):
        st.error("D1 ping {} failed".format(data.ip6_addr[1]))
        return False

    # D2 ping D1
    if not ipfeature.ping_poll(vars.D2, data.ip4_addr[0], family="ipv4", iter=3, count="4"):
        st.error("D2 ping {} failed".format(data.ip4_addr[0]))
        return False
    if not ipfeature.ping_poll(vars.D2, data.ip6_addr[0], family="ipv6", iter=3, count="4"):
        st.error("D1 ping {} failed".format(data.ip6_addr[0]))
        return False
    return True

def test_macsec_full_config():
    # 1. create profile
    st.log("create macsec profile {}".format(data.profile_name))
    ret = macsec_api.create_macsec_profile(vars.D1, data.profile_name, data.cipher_suite, data.primary_cak, data.primary_ckn)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(data.profile_name))

    # Get all interfaces
    output = st.show(vars.D1, "show interfaces status")
    for entry in output:
        # bypass breakout for Ethernet65_x
        if entry['interface'] and "Ethernet" in entry['interface'] and "_" not in entry['interface']:
            data.interfaces.append(entry['interface'])

    if len(data.interfaces) == 0:
        st.report_fail("Can't find any Ethernet interface")

    # enable all macsec port
    for interface in data.interfaces:
        ret = macsec_api.enable_macsec_port(vars.D1, interface, data.profile_name)
        if not ret:
            st.report_fail("Failed to enable macsec port {} with profile {}".format(interface, data.profile_name))

    # check wpa_supplicant
    st.wait(3)
    for interface in data.interfaces:
        ret = macsec_api.check_wpa_supplicant_process(vars.D1, interface)
        if not ret:
            st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(interface))

    # setup DUT2
    st.log("create macsec profile {}".format(data.profile_name))
    ret = macsec_api.create_macsec_profile(vars.D2, data.profile_name, data.cipher_suite, data.primary_cak, data.primary_ckn)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(data.profile_name))

    ret = macsec_api.enable_macsec_port(vars.D2, vars.D2D1P1, data.profile_name)
    if not ret:
        st.report_fail("Failed to enable macsec port {} with profile {}".format(interface, data.profile_name))

    st.wait(3)
    ret = macsec_api.check_wpa_supplicant_process(vars.D2, vars.D2D1P1)
    if not ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(interface))
    
    if not check_ping():
        st.report_fail("Ping failed")

    ###########################################
    # Reboot DUT1 and Check if the macsec was restored

    reboot.config_save_reboot(vars.D1)
    st.log("Wait another 200s for MACSec to initialize...")
    st.wait(200)

    # check wpa_supplicant
    st.wait(3)
    for interface in data.interfaces:
        ret = macsec_api.check_wpa_supplicant_process(vars.D1, interface)
        if not ret:
            st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(interface))

        output = macsec_api.show_macsec_connections(vars.D1, interface)
        if "TXSC" not in output:
            st.report_fail("TXSC is not created for the port {}.".format(interface))

    if not check_ping():
        st.report_fail("Ping failed")
    ###########################################

    st.report_pass("test_case_passed")
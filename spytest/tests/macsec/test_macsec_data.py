import pytest
import re

from spytest import st, tgapi, SpyTestDict
import apis.routing.ip as ipfeature
import apis.system.port as port_api
import apis.macsec.macsec as macsec_api

data = SpyTestDict()
data.primary_ckn = "3007"
data.primary_cak = "00112233445566778899001122334455"
data.primary_cak_64 = "0011223344556677889900112233445500112233445566778899001122334455"
data.primary_cak_wrong = "00112233445566778899001122334456"

data.profile = "GCM-AES-128-Profile"
data.cipher_suite = "GCM-AES-128"

data.ip4_addr = ["188.188.1.1", "188.188.1.2"]
data.ip6_addr = ["188::1", "188::2"]
data.af_ipv4 = "ipv4"
data.af_ipv6 = "ipv6"

MKA_TIMEOUT = 6

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
    destroy_macsec(vars.D1, vars.D1D2P1, data.profile)
    destroy_macsec(vars.D2, vars.D2D1P1, data.profile)

def setup_macsec(dut, port, profile_name, cipher_suite, cak="", sci=""):
    if cak:
        primary_cak = cak
    else:
        if "128" in cipher_suite:
            primary_cak = data.primary_cak
        else:
            primary_cak = data.primary_cak_64

    priority = 0
    policy = "security"
    if sci == "true" or sci == "false":
        send_sci = sci
    else:
        send_sci = "true"

    # 1. create profile
    st.log("create macsec profile {}".format(profile_name))
    ret = macsec_api.create_macsec_profile(dut, profile_name, cipher_suite, primary_cak, data.primary_ckn, priority, policy, send_sci)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(profile_name))

    # 2. enable port
    st.log("enable macsec port {} with profile {}".format(port, profile_name))
    ret = macsec_api.enable_macsec_port(dut, port, profile_name)
    if not ret:
        st.report_fail("Failed to enable macsec port {} with profile {}".format(port, profile_name))

    st.wait(4)

    # 3. check wpa_supplicant
    ret = macsec_api.check_wpa_supplicant_process(dut, port)
    if not ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(port))

def destroy_macsec(dut, port, profile_name):
    # disable macsec port
    ret = macsec_api.disable_macsec_port(dut, port)
    if not ret:
        st.report_fail("Failed to disable macsec port {}".format(port))

    # check wpa_supplicant, should not exist
    st.wait(4)
    ret = macsec_api.check_wpa_supplicant_process(dut, port)
    if ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't stopped.".format(port))

    # delete profile
    ret = macsec_api.delete_macsec_profile(dut, profile_name)
    if not ret:
        st.report_fail("Failed to delete macsec profile {}".format(profile_name))

def check_macsec(dut, port, cipher_suite):
    # DUT1
    output = macsec_api.show_macsec_connections(dut, port)
    if "RXSC" not in output:
        st.report_fail("Failed to setup macsec connections")

    if cipher_suite not in output:
        st.report_fail("cipher_suite is not expected")

    output = macsec_api.show_macsec_mka(dut, port)
    output = macsec_api.show_macsec_mib(dut, port)
    output = macsec_api.show_macsec_statistics(dut, port)

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

def test_macsec_mka_GCM_AES_128():
    data.profile = "GCM-AES-128-Profile"
    data.cipher_suite = "GCM-AES-128"

    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite)

    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)
    if not check_ping():
        st.report_fail("Ping failed")

    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)

    st.report_pass("test_case_passed")

def test_macsec_mka_GCM_AES_XPN_128():
    data.profile = "GCM-AES-XPN-128-Profile"
    data.cipher_suite = "GCM-AES-XPN-128"
    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite)

    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)
    if not check_ping():
        st.report_fail("Ping failed")
    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)

    st.report_pass("test_case_passed")

def test_macsec_mka_GCM_AES_256():
    data.profile = "GCM-AES-256-Profile"
    data.cipher_suite = "GCM-AES-256"
    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite)

    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)
    if not check_ping():
        st.report_fail("Ping failed")
    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)

    st.report_pass("test_case_passed")

def test_macsec_mka_GCM_AES_XPN_256():
    data.profile = "GCM-AES-XPN-256-Profile"
    data.cipher_suite = "GCM-AES-XPN-256"
    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite)

    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)
    if not check_ping():
        st.report_fail("Ping failed")
    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)

    st.report_pass("test_case_passed")

def test_macsec_linkflap():
    data.profile = "GCM-AES-128-Profile"
    data.cipher_suite = "GCM-AES-128"
    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite)

    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    check_macsec(vars.D2, vars.D2D1P1, data.cipher_suite)

    pre_connection = macsec_api.show_macsec_connections(vars.D1, vars.D1D2P1, False)
    st.log("Current Session TX AN {}".format(pre_connection[0]["tx_an"]))

    # Flap < 6 seconds
    command = "sudo ifconfig {} down && sleep {} && sudo ifconfig {} up".format(vars.D1D2P1, MKA_TIMEOUT-2, vars.D1D2P1)
    st.config(vars.D1, command)
    st.wait(3)
    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    cur_connection = macsec_api.show_macsec_connections(vars.D1, vars.D1D2P1, False)
    st.log("Current Session TX AN {}".format(cur_connection[0]["tx_an"]))
    if cur_connection[0]["tx_an"] != pre_connection[0]["tx_an"]:
        st.report_fail("The MKA session timeout")

    # Flap > 6 seconds
    command = "sudo ifconfig {} down && sleep {} && sudo ifconfig {} up".format(vars.D1D2P1, MKA_TIMEOUT+1, vars.D1D2P1)
    st.config(vars.D1, command)
    st.wait(3)
    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)
    cur_connection = macsec_api.show_macsec_connections(vars.D1, vars.D1D2P1, False)
    st.log("Current Session TX AN {}".format(cur_connection[0]["tx_an"]))
    if cur_connection[0]["tx_an"] == pre_connection[0]["tx_an"]:
        st.report_fail("The MKA session not timeout")

    if not check_ping():
        st.report_fail("Ping failed")

    # Flap, shut/noshut ports
    for i in range(5):
        st.wait(1)
        st.log("Bring port {} down".format(vars.D1D2P1))
        port_api.shutdown(vars.D1, [vars.D1D2P1])
        st.wait(MKA_TIMEOUT+1)
        st.log("Bring port {} up".format(vars.D1D2P1))
        port_api.noshutdown(vars.D1, [vars.D1D2P1])

    # Check mka session after flap
    st.wait(15)
    check_macsec(vars.D1, vars.D1D2P1, data.cipher_suite)

    if not check_ping():
        st.report_fail("Ping failed")

    st.report_pass("test_case_passed")

def test_macsec_cak_mismatch():
    data.profile = "GCM-AES-128-Profile"
    data.cipher_suite = "GCM-AES-128"

    # cak mismatch
    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite, data.primary_cak_wrong)

    # expect ping failed
    if check_ping():
        st.report_fail("Ping result is not expected")

    st.report_pass("test_case_passed")

def test_macsec_send_sci_mismatch():
    data.profile = "GCM-AES-128-Profile"
    data.cipher_suite = "GCM-AES-128"

    # cak mismatch
    setup_macsec(vars.D1, vars.D1D2P1, data.profile, data.cipher_suite)
    setup_macsec(vars.D2, vars.D2D1P1, data.profile, data.cipher_suite, sci="false")

    # expect ping failed
    if check_ping():
        st.report_fail("Ping result is not expected")

    st.report_pass("test_case_passed")
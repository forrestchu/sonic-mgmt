import pytest
import re

from spytest import st, tgapi, SpyTestDict
import apis.macsec.macsec as macsec_api

data = SpyTestDict()
data.primary_ckn = "3007"
data.primary_cak = "00112233445566778899001122334455"
data.primary_cak_64 = "0011223344556677889900112233445500112233445566778899001122334455"

@pytest.fixture(scope="module", autouse=True)
def macsec_module_hooks(request):
    global vars
    vars = st.ensure_min_topology("D1D2:1")

def setup_macsec(profile_name, cipher_suite):
    if "128" in cipher_suite:
        primary_cak = data.primary_cak
    else:
        primary_cak = data.primary_cak_64
    '''
    DUT1
    '''
    # 1. create profile
    st.log("create macsec profile {}".format(profile_name))
    ret = macsec_api.create_macsec_profile(vars.D1, profile_name, cipher_suite, primary_cak, data.primary_ckn)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(profile_name))

    # 2. enable port
    st.log("enable macsec port {} with profile {}".format(vars.D1D2P1, profile_name))
    ret = macsec_api.enable_macsec_port(vars.D1, vars.D1D2P1, profile_name)
    if not ret:
        st.report_fail("Failed to enable macsec port {} with profile {}".format(vars.D1D2P1, profile_name))

    st.wait(3)

    # 3. check wpa_supplicant
    ret = macsec_api.check_wpa_supplicant_process(vars.D1, vars.D1D2P1)
    if not ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(vars.D1D2P1))


    '''
    DUT2
    '''
    # 1. create profile
    st.log("create macsec profile {}".format(profile_name))
    ret = macsec_api.create_macsec_profile(vars.D2, profile_name, cipher_suite, primary_cak, data.primary_ckn)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(profile_name))

    # 2. enable port
    st.log("enable macsec port {} with profile {}".format(vars.D2D1P1, profile_name))
    ret = macsec_api.enable_macsec_port(vars.D2, vars.D2D1P1, profile_name)
    if not ret:
        st.report_fail("Failed to enable macsec port {} with profile {}".format(vars.D2D1P1, profile_name))

    st.wait(3)

    # 3. check wpa_supplicant
    ret = macsec_api.check_wpa_supplicant_process(vars.D2, vars.D2D1P1)
    if not ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(vars.D2D1P1))


def destroy_macsec(profile_name):
    '''
    DUT1
    '''
    # disable macsec port
    ret = macsec_api.disable_macsec_port(vars.D1, vars.D1D2P1)
    if not ret:
        st.report_fail("Failed to disable macsec port {}".format(vars.D1D2P1))

    # check wpa_supplicant, should not exist
    st.wait(3)
    ret = macsec_api.check_wpa_supplicant_process(vars.D1, vars.D1D2P1)
    if ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't stopped.".format(vars.D1D2P1))

    # delete profile
    ret = macsec_api.delete_macsec_profile(vars.D1, profile_name)
    if not ret:
        st.report_fail("Failed to delete macsec profile {}".format(profile_name))

    '''
    DUT2
    '''
    # disable macsec port
    ret = macsec_api.disable_macsec_port(vars.D2, vars.D2D1P1)
    if not ret:
        st.report_fail("Failed to disable macsec port {}".format(vars.D2D1P1))

    # check wpa_supplicant, should not exist
    st.wait(3)
    ret = macsec_api.check_wpa_supplicant_process(vars.D2, vars.D2D1P1)
    if ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't stopped.".format(vars.D2D1P1))

    # delete profile
    ret = macsec_api.delete_macsec_profile(vars.D2, profile_name)
    if not ret:
        st.report_fail("Failed to delete macsec profile {}".format(profile_name))

def check_macsec(cipher_suite):
    # DUT1
    output = macsec_api.show_macsec_connections(vars.D1, vars.D1D2P1)
    if "RXSC" not in output:
        st.report_fail("Failed to setup macsec connections")

    if cipher_suite not in output:
        st.report_fail("cipher_suite is not expected")

    output = macsec_api.show_macsec_mka(vars.D1, vars.D1D2P1)
    output = macsec_api.show_macsec_mib(vars.D1, vars.D1D2P1)


    # DUT2
    output = macsec_api.show_macsec_connections(vars.D2, vars.D2D1P1)
    if "RXSC" not in output:
        st.report_fail("Failed to setup macsec connections {}")

    if cipher_suite not in output:
        st.report_fail("cipher_suite is not expected")

    output = macsec_api.show_macsec_mka(vars.D2, vars.D2D1P1)
    output = macsec_api.show_macsec_mib(vars.D2, vars.D2D1P1)

@pytest.mark.regression
@pytest.mark.macsec
@pytest.mark.community
@pytest.mark.community_pass
def test_macsec_mka_GCM_AES_128():
    profile = "GCM-AES-128-Profile"
    cipher_suite = "GCM-AES-128"
    setup_macsec(profile, cipher_suite)

    check_macsec(cipher_suite)

    destroy_macsec(profile)
    st.report_pass("test_case_passed")

@pytest.mark.regression
@pytest.mark.macsec
@pytest.mark.community
@pytest.mark.community_pass
def test_macsec_mka_GCM_AES_XPN_128():
    profile = "GCM-AES-XPN-128-Profile"
    cipher_suite = "GCM-AES-XPN-128"
    setup_macsec(profile, cipher_suite)

    check_macsec(cipher_suite)

    destroy_macsec(profile)
    st.report_pass("test_case_passed")

@pytest.mark.regression
@pytest.mark.macsec
@pytest.mark.community
@pytest.mark.community_pass
def test_macsec_mka_GCM_AES_256():
    profile = "GCM-AES-256-Profile"
    cipher_suite = "GCM-AES-256"
    setup_macsec(profile, cipher_suite)

    check_macsec(cipher_suite)

    destroy_macsec(profile)
    st.report_pass("test_case_passed")

@pytest.mark.regression
@pytest.mark.macsec
@pytest.mark.community
@pytest.mark.community_pass
def test_macsec_mka_GCM_AES_XPN_256():
    profile = "GCM-AES-XPN-256-Profile"
    cipher_suite = "GCM-AES-XPN-256"
    setup_macsec(profile, cipher_suite)

    check_macsec(cipher_suite)

    destroy_macsec(profile)
    st.report_pass("test_case_passed")
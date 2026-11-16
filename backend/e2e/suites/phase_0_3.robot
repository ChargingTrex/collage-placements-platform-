*** Settings ***
Documentation     The existing 43-check halfway script, unchanged, on its own fresh database
...               with the plain seed (it compares exact result sets).
Library           Process
Library           OperatingSystem
Library           String

*** Variables ***
${BASE_URL}       http://127.0.0.1:8000
${PYTHON}         python
${BACKEND_DIR}    .

*** Test Cases ***
The Phase 0-3 Checkpoint Script Passes All 43 Checks
    [Documentation]    checkpoints/e2e_phase_0_3.py is run as a black box. It must exit 0 and say 43/43.
    ${result}=    Run Process    ${PYTHON}    checkpoints/e2e_phase_0_3.py    --base-url    ${BASE_URL}
    ...    cwd=${BACKEND_DIR}    timeout=900
    Log    ${result.stdout}
    Log    ${result.stderr}
    ${lines}=    Get Lines Matching Regexp    ${result.stdout}    ^\\d+/\\d+ checks passed
    Log To Console    ${SPACE*4}phase_0_3 script says: ${lines}
    Set Test Message    script output: ${lines}
    ${failures}=    Get Lines Matching Regexp    ${result.stdout}    ^FAIL
    Should Be Equal As Integers    ${result.rc}    0    msg=script exited ${result.rc}. Failing checks:\n${failures}
    Should Contain    ${result.stdout}    43/43 checks passed

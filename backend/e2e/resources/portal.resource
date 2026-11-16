*** Settings ***
Documentation     Shared keywords for every suite: one HTTP session, login, student
...               provisioning, status checks and the "not built yet" probe.
Library           RequestsLibrary
Library           Collections
Library           String
Library           OperatingSystem
Library           ../libraries/PortalLib.py

*** Variables ***
${BASE_URL}           http://127.0.0.1:8000
${PASSWORD}           E2e-Pass!2026x
${ADMIN_EMAIL}        placement.officer@college.edu
${ADMIN_PASSWORD}     AdminPass!234
${ACME_EMAIL}         recruiter@acmetech.example
${NIMBUS_EMAIL}       talent@nimbusanalytics.example
${COMPANY_PASSWORD}   CompanyPass!234

*** Keywords ***
Open Portal Session
    [Documentation]    One session for the suite; every call goes through `Api`.
    Create Session    api    ${BASE_URL}    timeout=120
    ${r}=    Api    GET    /api/health
    Status Is    ${r}    200

Api
    [Documentation]    One request. Never raises on an HTTP error: the test asserts the status.
    [Arguments]    ${method}    ${path}    ${token}=${None}    ${json}=${None}    ${files}=${None}    ${data}=${None}
    ${headers}=    Create Dictionary    Accept=*/*
    IF    $token
        Set To Dictionary    ${headers}    Authorization=Bearer ${token}
    END
    ${r}=    Run Keyword    ${method} On Session    api    ${path}    headers=${headers}
    ...    json=${json}    files=${files}    data=${data}    expected_status=any
    RETURN    ${r}

Status Is
    [Arguments]    ${r}    ${expected}
    Should Be Equal As Integers    ${r.status_code}    ${expected}
    ...    msg=${r.request.method} ${r.request.path_url} -> HTTP ${r.status_code} (wanted ${expected}): ${r.text}[:300]

Status Is One Of
    [Arguments]    ${r}    @{expected}
    ${code}=    Convert To String    ${r.status_code}
    ${wanted}=    Evaluate    [str(x) for x in $expected]
    Should Contain    ${wanted}    ${code}
    ...    msg=${r.request.method} ${r.request.path_url} -> HTTP ${code} (wanted one of ${wanted}): ${r.text}[:300]

Login
    [Documentation]    Returns the whole login response. Use `Access Token Of` for the token.
    [Arguments]    ${identifier}    ${password}
    ${r}=    Api    POST    /api/auth/login    json=${{ {"identifier": $identifier, "password": $password} }}
    RETURN    ${r}

Token For
    [Arguments]    ${identifier}    ${password}
    ${r}=    Login    ${identifier}    ${password}
    Status Is    ${r}    200
    RETURN    ${r.json()}[tokens][access]

Admin Token
    ${t}=    Token For    ${ADMIN_EMAIL}    ${ADMIN_PASSWORD}
    RETURN    ${t}

Acme Token
    ${t}=    Token For    ${ACME_EMAIL}    ${COMPANY_PASSWORD}
    RETURN    ${t}

Nimbus Token
    ${t}=    Token For    ${NIMBUS_EMAIL}    ${COMPANY_PASSWORD}
    RETURN    ${t}

Get Json
    [Arguments]    ${path}    ${token}=${None}    ${status}=200
    ${r}=    Api    GET    ${path}    ${token}
    Status Is    ${r}    ${status}
    RETURN    ${r.json()}

Post Json
    [Arguments]    ${path}    ${token}    ${body}=${None}    ${status}=200
    ${r}=    Api    POST    ${path}    ${token}    json=${body}
    Status Is    ${r}    ${status}
    RETURN    ${r}

All Pages
    [Documentation]    Every row of a paginated list, following `next`.
    [Arguments]    ${path}    ${token}
    @{rows}=    Create List
    ${url}=    Set Variable    ${path}
    WHILE    $url
        ${page}=    Get Json    ${url}    ${token}
        FOR    ${row}    IN    @{page}[results]
            Append To List    ${rows}    ${row}
        END
        ${url}=    Set Variable    ${page}[next]
        IF    $url and $url.startswith('http')
            ${url}=    Evaluate    '/' + $url.split('/', 3)[3]
        END
    END
    RETURN    ${rows}

Upload
    [Documentation]    Multipart upload of one file field.
    [Arguments]    ${path}    ${token}    ${filename}    ${content}    ${field}=file
    ${files}=    Evaluate    {$field: ($filename, $content)}
    ${r}=    Api    POST    ${path}    ${token}    files=${files}
    RETURN    ${r}

Provision Students
    [Documentation]    Upload a roster for `students`, then sign each one up, verify and log in.
    ...    Returns {prn: {token, refresh, student_id, claims, email}}.
    [Arguments]    ${students}    ${admin}
    ${csv}=    Roster Csv    ${students}
    ${r}=    Upload    /api/roster/upload    ${admin}    roster.csv    ${csv}
    Status Is    ${r}    200
    Should Be Equal As Integers    ${r.json()}[error_count]    0    msg=roster rows rejected: ${r.json()}
    ${out}=    Create Dictionary
    FOR    ${s}    IN    @{students}
        ${r}=    Api    POST    /api/auth/signup    json=${{ {"prn": $s["prn"], "email": $s["email"]} }}
        Status Is    ${r}    201
        ${otp}=    Get From Dictionary    ${r.json()}    debug_otp
        ${r}=    Api    POST    /api/auth/verify    json=${{ {"identifier": $s["prn"], "code": $otp, "password": $PASSWORD} }}
        Status Is    ${r}    200
        ${r}=    Login    ${s}[prn]    ${PASSWORD}
        Status Is    ${r}    200
        ${tokens}=    Set Variable    ${r.json()}[tokens]
        ${me}=    Get Json    /api/profiles/me    ${tokens}[access]
        ${entry}=    Create Dictionary    token=${tokens}[access]    refresh=${tokens}[refresh]
        ...    student_id=${me}[student_id]    email=${s}[email]    name=${s}[name]
        Set To Dictionary    ${out}    ${s}[prn]=${entry}
    END
    RETURN    ${out}

Upload Resume
    [Arguments]    ${token}    ${index}=0
    ${name}    ${content}=    Sample Resume    ${index}
    ${r}=    Upload    /api/profiles/me/resume    ${token}    ${name}    ${content}
    Status Is    ${r}    201
    RETURN    ${r}

Set Visibility
    [Arguments]    ${token}    ${value}
    ${r}=    Api    PUT    /api/profiles/me/visibility    ${token}    json=${{ {"visibility": $value} }}
    Status Is    ${r}    200

Probe Or Skip As Not Built
    [Documentation]    The ONE rule for "not built yet": this suite's probe route answers 404.
    ...    Any other answer (including 401/403/500) means the feature exists, and the tests run.
    [Arguments]    ${feature}    ${method}    ${path}    ${token}
    ${r}=    Api    ${method}    ${path}    ${token}
    IF    ${r.status_code} == 404
        Set Tags    not-built
        Skip    NOT BUILT: ${feature} (probe ${method} ${path} answered 404)
    END
    Log    probe ${method} ${path} answered ${r.status_code}: the feature is built, running its tests

Audit Count Should Grow By
    [Arguments]    ${before}    ${delta}    ${action}    ${target}=${None}
    ${after}=    Audit Count    ${action}    ${target}
    ${want}=    Evaluate    ${before} + ${delta}
    Should Be Equal As Integers    ${after}    ${want}    msg=audit '${action}' ${target}: ${before} -> ${after}, wanted +${delta}

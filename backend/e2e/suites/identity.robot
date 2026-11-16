*** Settings ***
Documentation     Identity journeys (checkpoint A): sign-in, the token claim contract, the JWKS,
...               refresh replay, suspension, the user directory, and company-scoped shortlists.
...               Students use PRN sequences 800-805 (batch 2078).
Resource          ../resources/portal.resource
Suite Setup       Prepare Identity Cohort
Suite Teardown    Delete All Sessions

*** Variables ***
@{CLAIMS}         sub    iss    aud    iat    exp    email    student_id    prn    display_name
...               roles    department    programme    year    mfa
${SECOND_RECRUITER}    second.recruiter@acmetech.example

*** Test Cases ***
Signup Then Verify Then Login Gives A Working Session
    ${admin}=    Admin Token
    ${s}=    Make Students    800    1    2078    tag=identity
    ${csv}=    Roster Csv    ${s}
    ${r}=    Upload    /api/roster/upload    ${admin}    one.csv    ${csv}
    Status Is    ${r}    200
    ${prn}=    Set Variable    ${s}[0][prn]
    ${r}=    Api    POST    /api/auth/signup    json=${{ {"prn": $prn, "email": $s[0]["email"]} }}
    Status Is    ${r}    201
    ${otp}=    Get From Dictionary    ${r.json()}    debug_otp
    ${r}=    Api    POST    /api/auth/login    json=${{ {"identifier": $prn, "password": $PASSWORD} }}
    Status Is One Of    ${r}    400    401    403
    ${r}=    Api    POST    /api/auth/verify    json=${{ {"identifier": $prn, "code": $otp, "password": $PASSWORD} }}
    Status Is    ${r}    200
    ${r}=    Login    ${prn}    ${PASSWORD}
    Status Is    ${r}    200
    ${token}=    Set Variable    ${r.json()}[tokens][access]
    ${me}=    Get Json    /api/auth/me    ${token}
    Should Be Equal    ${me}[prn]    ${prn}
    Should Be Equal    ${me}[roles]    ${{ ["student"] }}

Every Token Carries The Full Claim Set And An Array Of Roles
    ${student}=    Set Variable    ${COHORT}[220200801][token]
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    ${claims_student}=    Token Claims    ${student}
    ${claims_admin}=    Token Claims    ${admin}
    ${claims_company}=    Token Claims    ${acme}
    FOR    ${claims}    IN    ${claims_student}    ${claims_admin}    ${claims_company}
        FOR    ${key}    IN    @{CLAIMS}
            Dictionary Should Contain Key    ${claims}    ${key}    msg=claim '${key}' missing from ${claims}
        END
        Should Be True    isinstance($claims['roles'], list)
        Should Not Contain    ${claims}    role    msg=a singular 'role' claim is on the token
    END
    Should Be Equal    ${claims_student}[roles]    ${{ ["student"] }}
    Should Be Equal    ${claims_student}[prn]    220200801
    Should Be Equal    ${claims_student}[student_id]    ${COHORT}[220200801][student_id]
    Should Contain    ${claims_admin}[roles]    placement_admin
    Should Be Equal    ${claims_admin}[prn]    ${None}
    Should Be Equal    ${claims_admin}[student_id]    ${None}
    Length Should Be    ${claims_company}[roles]    1
    Should Start With    ${claims_company}[roles][0]    company_recruiter:
    ${scope}=    Evaluate    __import__('uuid').UUID($claims_company['roles'][0].split(':', 1)[1])
    Should Be Equal    ${{ sorted($claims_student) }}    ${{ sorted($claims_admin) }}
    ...    msg=token key sets differ by role: a claim is omitted rather than nulled

The JWKS Validates The Access Token
    ${r}=    Api    GET    /api/auth/jwks
    Status Is    ${r}    200
    ${jwks}=    Set Variable    ${r.json()}
    Should Not Be Empty    ${jwks}[keys]
    FOR    ${key}    IN    @{jwks}[keys]
        Should Be Equal    ${key}[kty]    RSA
        Should Not Be Empty    ${key}[kid]
    END
    ${claims}=    Verify Token Against Jwks    ${COHORT}[220200801][token]    ${jwks}
    Should Be Equal    ${claims}[prn]    220200801
    ${tampered}=    Set Variable    ${COHORT}[220200801][token]x
    Run Keyword And Expect Error    *    Verify Token Against Jwks    ${tampered}    ${jwks}

Replaying A Refresh Token Kills The Whole Session Family
    ${login}=    Login    220200802    ${PASSWORD}
    ${original}=    Set Variable    ${login.json()}[tokens][refresh]
    ${r}=    Api    POST    /api/auth/refresh    json=${{ {"refresh": $original} }}
    Status Is    ${r}    200
    ${rotated}=    Set Variable    ${r.json()}[refresh]
    Should Not Be Equal    ${rotated}    ${original}
    ${r}=    Api    POST    /api/auth/refresh    json=${{ {"refresh": $original} }}
    Status Is    ${r}    401
    ${r}=    Api    POST    /api/auth/refresh    json=${{ {"refresh": $rotated} }}
    Status Is    ${r}    401    # the replay revoked the rotated token too

Suspending A Student Kills Their Live Sessions
    ${a}=    Login    220200803    ${PASSWORD}
    ${b}=    Login    220200803    ${PASSWORD}
    ${token_a}=    Set Variable    ${a.json()}[tokens][access]
    ${token_b}=    Set Variable    ${b.json()}[tokens][access]
    ${r}=    Api    GET    /api/auth/me    ${token_a}
    Status Is    ${r}    200
    ${r}=    Api    GET    /api/auth/me    ${token_b}
    Status Is    ${r}    200
    Setup Via Manage Py Shell    suspend student 220200803
    ...    from accounts.models import User; User.objects.get(prn='220200803').set_status('suspended')
    ${r}=    Api    GET    /api/auth/me    ${token_a}
    Status Is    ${r}    401
    ${r}=    Api    GET    /api/auth/me    ${token_b}
    Status Is    ${r}    401
    ${r}=    Api    POST    /api/auth/refresh    json=${{ {"refresh": $a.json()["tokens"]["refresh"]} }}
    Status Is    ${r}    401
    ${r}=    Login    220200803    ${PASSWORD}
    Status Is One Of    ${r}    400    401    403

The User Directory Filters By PRN And Reports Unmatched PRNs
    ${admin}=    Admin Token
    ${page}=    Get Json    /api/auth/admin/users?prn=220200804    ${admin}
    Should Be Equal As Integers    ${page}[count]    1
    Should Be Equal    ${page}[results][0][prn]    220200804
    ${page}=    Get Json    /api/auth/admin/users?prns=220200804,220200805,220200899    ${admin}
    Should Be Equal As Integers    ${page}[count]    2
    Should Be Equal    ${page}[unmatched_prns]    ${{ ["220200899"] }}

Whitespace In A Filter Value Is Ignored
    ${admin}=    Admin Token
    ${page}=    Get Json    /api/auth/admin/users?prn=%20220200804%20    ${admin}
    Should Be Equal As Integers    ${page}[count]    1
    ${page}=    Get Json    /api/auth/admin/users?prns=220200804,%20220200805%20,%20220200899    ${admin}
    Should Be Equal As Integers    ${page}[count]    2
    Should Be Equal    ${page}[unmatched_prns]    ${{ ["220200899"] }}

An Unknown Query Parameter Is A 400
    ${admin}=    Admin Token
    ${r}=    Api    GET    /api/auth/admin/users?no_such_filter=1    ${admin}
    Status Is    ${r}    400
    ${r}=    Api    GET    /api/roster/students?prm=220200804    ${admin}
    Status Is    ${r}    400

Admins And Companies Are Identified By ADM And CMP Keys
    ${admin}=    Admin Token
    ${admins}=    Get Json    /api/auth/admin/users?role=admin    ${admin}
    Should Not Be Empty    ${admins}[results]
    FOR    ${row}    IN    @{admins}[results]
        Should Match Regexp    ${row}[human_key]    ^ADM-\\d{4}$
        Should Be Equal    ${row}[admin_id]    ${row}[human_key]
    END
    ${companies}=    Get Json    /api/auth/admin/users?role=company    ${admin}
    FOR    ${row}    IN    @{companies}[results]
        Should Match Regexp    ${row}[human_key]    ^CMP-\\d{4}$
    END
    ${first}=    Set Variable    ${admins}[results][0][admin_id]
    ${lower}=    Convert To Lower Case    ${first}
    ${page}=    Get Json    /api/auth/admin/users?admin_id=${lower}    ${admin}
    Should Be Equal As Integers    ${page}[count]    1    msg=the ADM- filter is not case-insensitive
    ${cmp}=    Set Variable    ${companies}[results][0][human_key]
    ${page}=    Get Json    /api/auth/admin/users?company_id=${cmp}    ${admin}
    Should Not Be Empty    ${page}[results]
    FOR    ${row}    IN    @{page}[results]
        Should Be Equal    ${row}[human_key]    ${cmp}
    END

Two Recruiters At One Company Share One Shortlist
    ${student}=    Set Variable    ${COHORT}[220200805]
    ${sid}=    Set Variable    ${student}[student_id]
    ${acme}=    Acme Token
    ${nimbus}=    Nimbus Token
    Setup Via Manage Py Shell    second recruiter at Acme Tech
    ...    from accounts.models import User, Company; c = Company.objects.get(name='Acme Tech'); User.objects.filter(email='${SECOND_RECRUITER}').exists() or User.objects.create_company(email='${SECOND_RECRUITER}', password='${COMPANY_PASSWORD}', company=c, full_name='Second Recruiter')
    ${colleague}=    Token For    ${SECOND_RECRUITER}    ${COMPANY_PASSWORD}
    Set Visibility    ${student}[token]    all
    ${r}=    Api    POST    /api/profiles/students/${sid}/shortlist    ${acme}    json=${{ {"note": "e2e"} }}
    Status Is    ${r}    201
    Set Visibility    ${student}[token]    shortlisted
    ${r}=    Api    GET    /api/profiles/students/${sid}    ${colleague}
    Status Is    ${r}    200    # the colleague at the same company sees what the shortlister sees
    ${page}=    Get Json    /api/profiles/students?prn=220200805    ${colleague}
    Should Be Equal As Integers    ${page}[count]    1
    ${r}=    Api    GET    /api/profiles/students/${sid}    ${nimbus}
    Status Is    ${r}    404
    ${r}=    Api    DELETE    /api/profiles/students/${sid}/shortlist    ${nimbus}
    Status Is    ${r}    404
    ${r}=    Api    GET    /api/profiles/students/${sid}    ${acme}
    Status Is    ${r}    200    # another company's attempt changed nothing
    ${r}=    Api    DELETE    /api/profiles/students/${sid}/shortlist    ${colleague}
    Status Is    ${r}    204
    ${r}=    Api    GET    /api/profiles/students/${sid}    ${acme}
    Status Is    ${r}    404    # one shared shortlist: the colleague's removal is the company's

*** Keywords ***
Prepare Identity Cohort
    Open Portal Session
    ${admin}=    Admin Token
    ${students}=    Make Students    801    5    2078    tag=identity
    ${cohort}=    Provision Students    ${students}    ${admin}
    Set Suite Variable    ${COHORT}    ${cohort}

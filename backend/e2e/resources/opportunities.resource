*** Settings ***
Documentation     Keywords for the Phase B / Addendum 2 endpoints, written against
...               docs/OPPORTUNITIES_API_CONTRACT.md. Not yet run against a real backend.
Resource          portal.resource

*** Variables ***
${JD_BACKEND}     Backend Engineer. Build and ship REST APIs in Python and Django, backed by PostgreSQL, deployed with Docker. Git and code review every day.
${DEPT_CS}        B.Tech Computer Science
${DEPT_BBA}       BBA (Hons.)

*** Keywords ***
Rows Of
    [Documentation]    The rows of a list response, whether it is paginated ({results}) or a bare array.
    ...    ASSUMPTION: the contract does not say whether feed and notifications are paginated.
    [Arguments]    ${doc}
    ${rows}=    Evaluate    $doc['results'] if isinstance($doc, dict) and 'results' in $doc else $doc
    RETURN    ${rows}

Future Date
    [Arguments]    ${days}
    ${d}=    Evaluate    (__import__('datetime').date.today() + __import__('datetime').timedelta(days=int($days))).isoformat()
    RETURN    ${d}

Company Id Of
    [Documentation]    The company UUID, read from the recruiter token's company_recruiter:<uuid> role.
    [Arguments]    ${token}
    ${claims}=    Token Claims    ${token}
    ${scoped}=    Evaluate    [r for r in $claims['roles'] if r.startswith('company_recruiter:')][0]
    ${id}=    Evaluate    $scoped.split(':', 1)[1]
    RETURN    ${id}

Opportunity Body
    [Arguments]    ${title}=Backend Engineer    ${days}=30    ${min_cgpa}=7.5    ${departments}=${None}    &{extra}
    ${departments}=    Evaluate    $departments if $departments is not None else ["B.Tech Computer Science"]
    ${deadline}=    Future Date    ${days}
    ${body}=    Create Dictionary    title=${title}    description=${JD_BACKEND}    role_type=full_time
    ...    location=Pune    openings=2    required_skills=${{ ["Python", "Django"] }}
    ...    eligible_departments=${departments}    min_cgpa=${min_cgpa}    salary_disclosed=${False}
    ...    deadline=${deadline}
    Set To Dictionary    ${body}    &{extra}
    RETURN    ${body}

Admin Creates Open Opportunity
    [Documentation]    Admin POST is created `open` straight away (D28) and needs `company`.
    [Arguments]    ${admin}    ${company_id}    &{kwargs}
    ${body}=    Opportunity Body    &{kwargs}
    Set To Dictionary    ${body}    company=${company_id}
    ${r}=    Api    POST    /api/opportunities/    ${admin}    json=${body}
    Status Is    ${r}    201
    Should Be Equal    ${r.json()}[status]    open
    RETURN    ${r.json()}

Apply
    [Arguments]    ${token}    ${opportunity_id}
    ${r}=    Api    POST    /api/opportunities/${opportunity_id}/apply    ${token}
    RETURN    ${r}

Apply Should Be Refused
    [Arguments]    ${token}    ${opportunity_id}    ${reason}
    ${r}=    Apply    ${token}    ${opportunity_id}
    Status Is    ${r}    400
    Should Be Equal    ${r.json()}[reason]    ${reason}    msg=refusal reason: ${r.text}

Set Application Status
    [Arguments]    ${token}    ${application_id}    ${status}    ${expect}=200
    ${r}=    Api    POST    /api/opportunities/applications/${application_id}/status    ${token}    json=${{ {"status": $status, "note": "e2e"} }}
    Status Is    ${r}    ${expect}
    RETURN    ${r}

Notifications Of
    [Arguments]    ${token}    ${kind}=${None}
    ${doc}=    Get Json    /api/notifications/    ${token}
    ${rows}=    Rows Of    ${doc}
    IF    $kind
        ${rows}=    Evaluate    [n for n in $rows if n['kind'] == $kind]
    END
    RETURN    ${rows}

Can See Profile
    [Documentation]    True when the company can open the student's profile (200), False on 404.
    [Arguments]    ${company_token}    ${student_id}
    ${r}=    Api    GET    /api/profiles/students/${student_id}    ${company_token}
    Status Is One Of    ${r}    200    404
    ${seen}=    Evaluate    ${r.status_code} == 200
    RETURN    ${seen}

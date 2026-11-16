*** Settings ***
Documentation     Stage 3: GET /api/opportunities/suggestions (docs/OPPORTUNITIES_API_CONTRACT.md).
...               Students use PRN sequences 860-863 (batch 2074). Probe route: that same URL.
...               The server runs with the LLM off (run.py forces it), so every check here is also
...               "works with the AI off".
Resource          ../resources/opportunities.resource
Suite Setup       Prepare Suggestions
Suite Teardown    Delete All Sessions

*** Variables ***
${URL}            /api/opportunities/suggestions
${JD_MECHANICAL}  Graduate Design Engineer. Model sheet metal and moulded parts for automotive assemblies in SolidWorks and AutoCAD, GD&T, FEA with ANSYS.

*** Test Cases ***
With Nothing Posted The Answer Says So
    ${r}=    Api    GET    ${URL}    ${STUDENT}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[reason]    no_open_postings
    Should Be Equal As Integers    ${r.json()}[open_count]    0
    Should Be Empty    ${r.json()}[results]

Suggestions Are Ranked, Above The Cut-Off And Shaped Like The Feed
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    ${cid}=    Company Id Of    ${acme}
    ${backend}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Backend Role    similarity_threshold=${0}
    ${mech}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Design Role    similarity_threshold=${0}
    ...    description=${JD_MECHANICAL}    required_skills=${{ ["SolidWorks", "AutoCAD"] }}
    Set Suite Variable    ${BACKEND_OPP}    ${backend}[id]
    Set Suite Variable    ${MECH_OPP}    ${mech}[id]
    ${r}=    Api    GET    ${URL}    ${STUDENT}
    Status Is    ${r}    200
    ${body}=    Set Variable    ${r.json()}
    Should Be Equal As Integers    ${body}[open_count]    2
    Should Be Equal    ${body}[reason]    ${None}
    ${rows}=    Set Variable    ${body}[results]
    Length Should Be    ${rows}    2
    ${scores}=    Evaluate    [row['score'] for row in $rows]
    Should Be Equal    ${scores}    ${{ sorted($scores, reverse=True) }}    msg=suggestions must be sorted by score, best first
    ${ids}=    Evaluate    [row['id'] for row in $rows]
    Should Be Equal    ${ids}[0]    ${BACKEND_OPP}    msg=the backend resume should rank the backend role first
    FOR    ${row}    IN    @{rows}
        FOR    ${key}    IN    score    components    matched_skills    missing_skills    eligible    eligibility_reasons    has_applied    application_status
            Dictionary Should Contain Key    ${row}    ${key}
        END
        Should Be True    isinstance($row['score'], int) and 0 <= $row['score'] <= 100
    END

An Opportunity Past Its Deadline Drops Out
    Setup Via Manage Py Shell    move the design role's deadline to yesterday
    ...    from opportunities.models import Opportunity; import datetime; Opportunity.objects.filter(id='${MECH_OPP}').update(deadline=datetime.date.today() - datetime.timedelta(days=1))
    ${r}=    Api    GET    ${URL}    ${STUDENT}
    Status Is    ${r}    200
    ${ids}=    Evaluate    [row['id'] for row in $r.json()['results']]
    Should Be Equal    ${ids}    ${{ [$BACKEND_OPP] }}
    Should Be Equal As Integers    ${r.json()}[open_count]    1

When Nothing Fits Well The Answer Says That Instead
    Setup Via Manage Py Shell    close the earlier postings and raise the bar on a new one
    ...    from opportunities.models import Opportunity; Opportunity.objects.filter(status='open').update(status='closed')
    ${admin}=    Admin Token
    ${cid}=    Company Id Of    ${ACME}
    ${strict}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Impossible Bar    similarity_threshold=${100}
    ...    description=${JD_MECHANICAL}
    ${r}=    Api    GET    ${URL}    ${STUDENT}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[reason]    none_match
    Should Be Equal As Integers    ${r.json()}[open_count]    1
    Should Be Empty    ${r.json()}[results]

The Page Never Says Probability
    ${feed}=    Api    GET    /api/opportunities/feed    ${STUDENT}
    Status Is    ${feed}    200
    ${r}=    Api    GET    ${URL}    ${STUDENT}
    Status Is    ${r}    200
    FOR    ${text}    IN    ${r.text}    ${feed.text}
        ${lower}=    Convert To Lower Case    ${text}
        Should Not Contain    ${lower}    probab
        Should Not Contain    ${lower}    chance of
        Should Not Contain    ${lower}    likelihood
    END

Only Students May Ask
    ${r}=    Api    GET    ${URL}    ${ACME}
    Status Is    ${r}    403
    ${admin}=    Admin Token
    ${r}=    Api    GET    ${URL}    ${admin}
    Status Is    ${r}    403
    ${r}=    Api    GET    ${URL}
    Status Is    ${r}    401
    ${r}=    Api    GET    ${URL}?surprise=1    ${STUDENT}
    Status Is    ${r}    400    # an unknown query parameter is a 400

*** Keywords ***
Prepare Suggestions
    Open Portal Session
    ${admin}=    Admin Token
    Probe Or Skip As Not Built    suggestions    GET    ${URL}    ${admin}
    ${students}=    Make Students    860    2    2074    tag=suggest
    ${cohort}=    Provision Students    ${students}    ${admin}
    Upload Resume    ${cohort}[220200860][token]    0
    Set Visibility    ${cohort}[220200860][token]    all
    Set Suite Variable    ${STUDENT}    ${cohort}[220200860][token]
    ${acme}=    Acme Token
    Set Suite Variable    ${ACME}    ${acme}
    # Other suites may share this database and have left postings open: the
    # "nothing posted" state needs a clean slate. Labelled setup, not a journey.
    Setup Via Manage Py Shell    close every posting left open by earlier suites
    ...    from opportunities.models import Opportunity; Opportunity.objects.filter(status='open').update(status='closed')

*** Settings ***
Documentation     Phase B journeys (docs/OPPORTUNITIES_API_CONTRACT.md, Stage 2): posting, approval,
...               notifications, the feed, applying, shortlist rules (D27), status events, screening,
...               the applicant CSV, admin stats and notify_deadlines.
...               Students use PRN sequences 820-829 (batch 2076). Probe route: GET /api/opportunities/.
Resource          ../resources/opportunities.resource
Suite Setup       Prepare Phase B
Suite Teardown    Delete All Sessions

*** Variables ***
${CSV_HEADER}     prn,full_name,department,programme,school,batch,cgpa_at_apply,status,score,applied_at,email,phone,contact_available

*** Test Cases ***
A Recruiter Posts, It Waits For Approval, And Students Cannot See It
    ${acme}=    Acme Token
    ${nimbus}=    Nimbus Token
    ${body}=    Opportunity Body    title=Recruiter Posted Role
    ${r}=    Api    POST    /api/opportunities/    ${acme}    json=${body}
    Status Is    ${r}    201
    ${opp}=    Set Variable    ${r.json()}
    Should Be Equal    ${opp}[status]    draft
    Set Suite Variable    ${DRAFT_ID}    ${opp}[id]
    ${student}=    Set Variable    ${COHORT}[220200820][token]
    ${r}=    Api    GET    /api/opportunities/${DRAFT_ID}    ${student}
    Status Is    ${r}    404
    ${r}=    Api    POST    /api/opportunities/${DRAFT_ID}/submit    ${acme}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[status]    pending_review
    ${doc}=    Get Json    /api/opportunities/    ${student}
    ${ids}=    Evaluate    [o['id'] for o in $doc['results']] if isinstance($doc, dict) else [o['id'] for o in $doc]
    Should Not Contain    ${ids}    ${DRAFT_ID}
    ${r}=    Api    POST    /api/opportunities/${DRAFT_ID}/approve    ${acme}
    Status Is One Of    ${r}    403    404
    ${r}=    Api    GET    /api/opportunities/${DRAFT_ID}    ${nimbus}
    Status Is    ${r}    404
    ${r}=    Api    GET    /api/opportunities/${DRAFT_ID}    ${admin}
    Status Is    ${r}    200

The Admin Approves It And Eligible Students Are Notified
    ${admin}=    Admin Token
    ${before_ok}=    Notifications Of    ${COHORT}[220200820][token]    new_opportunity
    ${r}=    Api    POST    /api/opportunities/${DRAFT_ID}/approve    ${admin}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[status]    open
    ${r}=    Api    POST    /api/opportunities/${DRAFT_ID}/approve    ${admin}
    Status Is    ${r}    400    # already open
    ${student}=    Set Variable    ${COHORT}[220200820][token]
    ${r}=    Api    GET    /api/opportunities/${DRAFT_ID}    ${student}
    Status Is    ${r}    200
    ${mine}=    Notifications Of    ${student}    new_opportunity
    ${hits}=    Evaluate    [n for n in $mine if n['opportunity']['id'] == $DRAFT_ID]
    Length Should Be    ${hits}    1
    # not eligible: wrong department, and a CGPA under the cut-off
    FOR    ${prn}    IN    220200826    220200827
        ${theirs}=    Notifications Of    ${COHORT}[${prn}][token]    new_opportunity
        ${hits}=    Evaluate    [n for n in $theirs if n['opportunity']['id'] == $DRAFT_ID]
        Should Be Empty    ${hits}    msg=${prn} is not eligible but was notified
    END
    # reading: one, then all
    ${unread}=    Get Json    /api/notifications/?unread=true    ${student}
    ${rows}=    Rows Of    ${unread}
    Should Not Be Empty    ${rows}
    ${r}=    Api    POST    /api/notifications/${rows}[0][id]/read    ${student}
    Status Is    ${r}    204
    ${r}=    Api    POST    /api/notifications/read-all    ${student}
    Status Is    ${r}    204
    ${unread}=    Get Json    /api/notifications/?unread=true    ${student}
    Should Be Empty    ${{ $unread['results'] if isinstance($unread, dict) else $unread }}
    # another student's notification is not reachable
    ${theirs}=    Notifications Of    ${COHORT}[220200821][token]
    ${r}=    Api    POST    /api/notifications/${theirs}[0][id]/read    ${student}
    Status Is    ${r}    404

A Rejection Needs A Reason And Keeps The Posting Hidden
    ${acme}=    Acme Token
    ${admin}=    Admin Token
    ${body}=    Opportunity Body    title=Rejected Role
    ${r}=    Api    POST    /api/opportunities/    ${acme}    json=${body}
    Status Is    ${r}    201
    ${id}=    Set Variable    ${r.json()}[id]
    ${r}=    Api    POST    /api/opportunities/${id}/submit    ${acme}
    Status Is    ${r}    200
    ${r}=    Api    POST    /api/opportunities/${id}/reject    ${admin}    json=${{ {} }}
    Status Is    ${r}    400    # the reason is required
    ${r}=    Api    POST    /api/opportunities/${id}/reject    ${admin}    json=${{ {"reason": "Salary range missing."} }}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[status]    rejected
    ${r}=    Api    GET    /api/opportunities/${id}    ${COHORT}[220200820][token]
    Status Is    ${r}    404
    ${r}=    Api    PATCH    /api/opportunities/${id}    ${acme}    json=${{ {"title": "Rejected Role, revised"} }}
    Status Is    ${r}    200    # a recruiter may edit a rejected posting
    ${r}=    Api    POST    /api/opportunities/${id}/submit    ${acme}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[status]    pending_review

The Feed Ranks The Matching Student Higher
    ${backend_student}=    Set Variable    ${COHORT}[220200820][token]
    ${other_student}=    Set Variable    ${COHORT}[220200821][token]
    ${doc_a}=    Get Json    /api/opportunities/feed    ${backend_student}
    ${doc_b}=    Get Json    /api/opportunities/feed    ${other_student}
    ${rows_a}=    Rows Of    ${doc_a}
    ${rows_b}=    Rows Of    ${doc_b}
    ${a}=    Evaluate    [o for o in $rows_a if o['id'] == $DRAFT_ID][0]
    ${b}=    Evaluate    [o for o in $rows_b if o['id'] == $DRAFT_ID][0]
    Should Be True    ${a}[score] > ${b}[score]    msg=backend resume scored ${a}[score], mechanical resume ${b}[score]
    FOR    ${key}    IN    score    components    matched_skills    missing_skills    eligible    eligibility_reasons    has_applied    application_status
        Dictionary Should Contain Key    ${a}    ${key}
    END
    ${scores}=    Evaluate    [o['score'] for o in $rows_a]
    Should Be Equal    ${scores}    ${{ sorted($scores, reverse=True) }}    msg=the feed is not ordered by score
    Should Be True    ${a}[eligible]

Applying Is Refused For Each Reason And Succeeds Otherwise
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    ${cid}=    Company Id Of    ${acme}
    ${opp}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Apply Journey
    Set Suite Variable    ${OPP_ID}    ${opp}[id]
    # no resume
    Apply Should Be Refused    ${COHORT}[220200824][token]    ${OPP_ID}    no_resume
    # wrong department, and a CGPA under the cut-off (both have a resume, so only eligibility can refuse them)
    Apply Should Be Refused    ${COHORT}[220200826][token]    ${OPP_ID}    not_eligible
    Apply Should Be Refused    ${COHORT}[220200827][token]    ${OPP_ID}    not_eligible
    # the real application
    ${r}=    Apply    ${COHORT}[220200820][token]    ${OPP_ID}
    Status Is    ${r}    201
    Should Be Equal    ${r.json()}[status]    applied
    Should Be Equal    ${r.json()}[prn]    220200820
    Should Be Equal As Numbers    ${r.json()}[cgpa_at_apply]    8.50
    Set Suite Variable    ${APP_820}    ${r.json()}[id]
    Apply Should Be Refused    ${COHORT}[220200820][token]    ${OPP_ID}    already_applied
    # a closed posting and one past its deadline
    ${closed}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Soon Closed
    ${r}=    Api    POST    /api/opportunities/${closed}[id]/close    ${acme}
    Status Is    ${r}    200
    Apply Should Be Refused    ${COHORT}[220200821][token]    ${closed}[id]    not_open
    ${late}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Past Deadline
    Setup Via Manage Py Shell    move one posting's deadline to yesterday
    ...    from opportunities.models import Opportunity; import datetime; Opportunity.objects.filter(id='${late}[id]').update(deadline=datetime.date.today() - datetime.timedelta(days=1))
    Apply Should Be Refused    ${COHORT}[220200821][token]    ${late}[id]    deadline_passed

The Application Freezes The Roster CGPA And A Copy Of The Resume
    ${acme}=    Acme Token
    ${student}=    Set Variable    ${COHORT}[220200820]
    ${name}    ${original}=    Sample Resume    0
    Setup Via Manage Py Shell    the roster CGPA changes after the student applied
    ...    from roster.models import Student; Student.objects.filter(prn='220200820').update(cgpa='6.10')
    ${other_name}    ${other_bytes}=    Sample Resume    3
    ${r}=    Upload    /api/profiles/me/resume    ${student}[token]    ${other_name}    ${other_bytes}
    Status Is    ${r}    201
    ${app}=    Get Json    /api/opportunities/applications/${APP_820}    ${student}[token]
    Should Be Equal As Numbers    ${app}[cgpa_at_apply]    8.50    msg=the frozen CGPA followed the roster
    Should Be Equal    ${app}[full_name]    ${student}[name]
    Should Not Be Empty    ${app}[events]
    Should Be Equal    ${app}[events][0][to_status]    applied
    ${r}=    Api    GET    /api/opportunities/applications/${APP_820}/resume    ${student}[token]
    Status Is    ${r}    200
    Should Be True    $r.content == $original    msg=the application's resume is not the copy taken at apply time
    ${before}=    Audit Count    document_accessed
    ${r}=    Api    GET    /api/opportunities/applications/${APP_820}/resume    ${acme}
    Status Is    ${r}    200
    Should Be True    $r.content == $original
    Audit Count Should Grow By    ${before}    1    document_accessed

Company Application Payloads Are An Allow List
    ${acme}=    Acme Token
    ${doc}=    Get Json    /api/opportunities/applications?opportunity=${OPP_ID}    ${acme}
    ${rows}=    Rows Of    ${doc}
    Should Not Be Empty    ${rows}
    ${leaked}=    Keys Starting With    ${rows}    career_path    transcript    parsed_cgpa    recomputed_cgpa    confirmed_cgpa
    ...    personal_email    also_attending_placements    marks_    events    profile_student_id
    Should Be Empty    ${leaked}    msg=company application payload carries ${leaked}
    FOR    ${row}    IN    @{rows}
        Should Be True    $row['contact'] is None or set($row['contact']) == {'email', 'phone'}
        Should Be Equal    ${{ $row['contact'] is not None }}    ${row}[contact_available]
    END

A Hidden Student Can Apply But Stays Out Of Browse
    ${acme}=    Acme Token
    ${hidden}=    Set Variable    ${COHORT}[220200825]
    Set Visibility    ${hidden}[token]    hidden
    ${r}=    Apply    ${hidden}[token]    ${OPP_ID}
    Status Is    ${r}    201
    ${doc}=    Get Json    /api/opportunities/applications?opportunity=${OPP_ID}&prn=220200825    ${acme}
    Length Should Be    ${{ $doc['results'] if isinstance($doc, dict) else $doc }}    1
    ${page}=    Get Json    /api/profiles/students?prn=220200825    ${acme}
    Should Be Equal As Integers    ${page}[count]    0
    ${seen}=    Can See Profile    ${acme}    ${hidden}[student_id]
    Should Not Be True    ${seen}

Withdrawing Removes An Applicant's Access Only If The Application Granted It
    ${acme}=    Acme Token
    ${admin}=    Admin Token
    ${cid}=    Company Id Of    ${acme}
    ${opp}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Shortlist Rules
    # 1. application grants visibility; withdrawing takes it away
    ${s}=    Set Variable    ${COHORT}[220200822]
    Set Visibility    ${s}[token]    shortlisted
    ${seen}=    Can See Profile    ${acme}    ${s}[student_id]
    Should Not Be True    ${seen}
    ${r}=    Apply    ${s}[token]    ${opp}[id]
    Status Is    ${r}    201
    ${seen}=    Can See Profile    ${acme}    ${s}[student_id]
    Should Be True    ${seen}
    ${r2}=    Api    POST    /api/opportunities/applications/${r.json()}[id]/withdraw    ${s}[token]
    Status Is    ${r2}    200
    Should Be Equal    ${r2.json()}[status]    withdrawn
    ${seen}=    Can See Profile    ${acme}    ${s}[student_id]
    Should Not Be True    ${seen}
    ${r3}=    Api    POST    /api/opportunities/applications/${r.json()}[id]/withdraw    ${s}[token]
    Status Is    ${r3}    400    # already withdrawn
    # 2. a manual shortlist survives the student's withdrawal
    ${m}=    Set Variable    ${COHORT}[220200823]
    Set Visibility    ${m}[token]    all
    ${r}=    Api    POST    /api/profiles/students/${m}[student_id]/shortlist    ${acme}    json=${{ {"note": "e2e"} }}
    Status Is    ${r}    201
    Set Visibility    ${m}[token]    shortlisted
    ${app}=    Apply    ${m}[token]    ${opp}[id]
    Status Is    ${app}    201
    ${r}=    Api    POST    /api/opportunities/applications/${app.json()}[id]/withdraw    ${m}[token]
    Status Is    ${r}    200
    ${seen}=    Can See Profile    ${acme}    ${m}[student_id]
    Should Be True    ${seen}    msg=a manual shortlist row was removed by the student's withdrawal
    # 3. un-shortlisting someone who has a live application leaves them visible
    ${app}=    Apply    ${m}[token]    ${opp}[id]
    Status Is One Of    ${app}    201    400    # a withdrawn application may or may not be re-openable
    ${r}=    Api    DELETE    /api/profiles/students/${m}[student_id]/shortlist    ${acme}
    Status Is    ${r}    204
    ${seen}=    Can See Profile    ${acme}    ${m}[student_id]
    Should Not Be True    ${seen}    msg=with no live application, un-shortlisting must hide a shortlisted-only profile

Status Moves Are Recorded As Events And A Bad Move Is A 400
    ${acme}=    Acme Token
    ${nimbus}=    Nimbus Token
    ${student}=    Set Variable    ${COHORT}[220200820][token]
    ${bad}=    Set Application Status    ${acme}    ${APP_820}    offer    400    # applied -> offer skips two steps
    ${bad}=    Set Application Status    ${acme}    ${APP_820}    no_such_status    400
    ${nope}=    Set Application Status    ${student}    ${APP_820}    shortlisted    403    # a student cannot move it
    ${nope}=    Set Application Status    ${nimbus}    ${APP_820}    shortlisted    404    # another company cannot see it
    ${audit}=    Audit Count    application_status_changed
    Set Application Status    ${acme}    ${APP_820}    shortlisted
    Set Application Status    ${acme}    ${APP_820}    interview
    Set Application Status    ${acme}    ${APP_820}    offer
    ${bad}=    Set Application Status    ${acme}    ${APP_820}    applied    400    # nothing moves backwards
    ${app}=    Get Json    /api/opportunities/applications/${APP_820}    ${student}
    ${path}=    Evaluate    [(e['from_status'], e['to_status']) for e in $app['events']]
    Should Be Equal    ${path}    ${{ [("", "applied"), ("applied", "shortlisted"), ("shortlisted", "interview"), ("interview", "offer")] }}
    ${r}=    Api    POST    /api/opportunities/applications/${APP_820}/withdraw    ${student}
    Status Is    ${r}    400    # offer is a final status

Bulk Screening Splits Applicants Three Ways
    ${acme}=    Acme Token
    ${r}=    Api    POST    /api/opportunities/${OPP_ID}/screen    ${acme}    json=${{ {"threshold": 0} }}
    Status Is    ${r}    200
    FOR    ${key}    IN    shortlisted    below_threshold    filtered_out
        Dictionary Should Contain Key    ${r.json()}    ${key}
    END
    ${everyone}=    Evaluate    $r.json()['shortlisted'] + $r.json()['below_threshold'] + $r.json()['filtered_out']
    ${prns}=    Evaluate    sorted(x['prn'] for x in $everyone)
    Should Contain    ${prns}    220200820
    Should Contain    ${prns}    220200825
    FOR    ${row}    IN    @{everyone}
        FOR    ${key}    IN    application_id    prn    full_name    score    experience_years    education_levels    reasons
            Dictionary Should Contain Key    ${row}    ${key}
        END
    END
    ${strict}=    Api    POST    /api/opportunities/${OPP_ID}/screen    ${acme}    json=${{ {"threshold": 101} }}
    Status Is    ${strict}    200
    Should Be Empty    ${strict.json()}[shortlisted]    msg=nobody can reach a threshold of 101
    ${filtered}=    Api    POST    /api/opportunities/${OPP_ID}/screen    ${acme}    json=${{ {"threshold": 0, "min_experience_years": 50} }}
    Status Is    ${filtered}    200
    Should Be Empty    ${filtered.json()}[shortlisted]    msg=nobody has 50 years of experience
    Should Not Be Empty    ${filtered.json()}[filtered_out]
    ${r}=    Api    POST    /api/opportunities/${OPP_ID}/screen    ${COHORT}[220200820][token]    json=${{ {} }}
    Status Is One Of    ${r}    403    404

The Applicant CSV Has The PRN First And Is Audited
    ${acme}=    Acme Token
    ${nimbus}=    Nimbus Token
    ${before}=    Audit Count    applications_exported
    ${r}=    Api    GET    /api/opportunities/${OPP_ID}/applicants/export    ${acme}
    Status Is    ${r}    200
    Should Contain    ${r.headers}[Content-Type]    text/csv
    ${rows}=    Parse Csv    ${r.text}
    Should Be Equal    ${{ ",".join($rows[0]) }}    ${CSV_HEADER}
    Should Be Equal    ${rows}[0][0]    prn
    ${body}=    Evaluate    $rows[1:]
    Should Not Be Empty    ${body}
    ${scores}=    Evaluate    [(-int(float(r[8])), r[0]) for r in $body]
    Should Be Equal    ${scores}    ${{ sorted($scores) }}    msg=rows must be sorted by score desc, then PRN
    FOR    ${row}    IN    @{body}
        Should Match Regexp    ${row}[0]    ^\\d{9}$
        IF    '${row}[12]'.lower() == 'false'
            Should Be Empty    ${row}[10]
            Should Be Empty    ${row}[11]
        END
    END
    Audit Count Should Grow By    ${before}    1    applications_exported
    ${r}=    Api    GET    /api/opportunities/${OPP_ID}/applicants/export    ${nimbus}
    Status Is    ${r}    404
    ${r}=    Api    GET    /api/opportunities/${OPP_ID}/applicants/export    ${COHORT}[220200820][token]
    Status Is One Of    ${r}    403    404

Admin Stats Add Up
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    ${stats}=    Get Json    /api/opportunities/stats    ${admin}
    FOR    ${key}    IN    opportunities_by_status    applications_by_status    per_opportunity    median_hours_to_shortlist
        Dictionary Should Contain Key    ${stats}    ${key}
    END
    ${apps}=    Evaluate    sum($stats['applications_by_status'].values())
    ${per}=    Evaluate    sum(o['applicants'] for o in $stats['per_opportunity'])
    Should Be Equal As Integers    ${apps}    ${per}    msg=applications_by_status and per_opportunity disagree
    Should Be True    ${stats}[opportunities_by_status][open] >= 1
    ${r}=    Api    GET    /api/opportunities/stats    ${acme}
    Status Is    ${r}    403

Deadline Reminders Go Out Once Even When The Command Runs Twice
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    ${cid}=    Company Id Of    ${acme}
    ${opp}=    Admin Creates Open Opportunity    ${admin}    ${cid}    title=Closing Soon    days=2
    ${applied}=    Set Variable    ${COHORT}[220200822]
    ${waiting}=    Set Variable    ${COHORT}[220200821]
    ${r}=    Apply    ${applied}[token]    ${opp}[id]
    Status Is One Of    ${r}    201    400
    Setup Via Manage Py    run notify_deadlines (first time)    notify_deadlines
    ${first}=    Notifications Of    ${waiting}[token]    deadline_soon
    ${first_mine}=    Evaluate    [n for n in $first if n['opportunity']['id'] == $opp['id']]
    Length Should Be    ${first_mine}    1
    Setup Via Manage Py    run notify_deadlines (second time)    notify_deadlines
    ${again}=    Notifications Of    ${waiting}[token]    deadline_soon
    ${again_mine}=    Evaluate    [n for n in $again if n['opportunity']['id'] == $opp['id']]
    Length Should Be    ${again_mine}    1    msg=the second run sent the reminder again
    ${theirs}=    Notifications Of    ${applied}[token]    deadline_soon
    ${theirs_mine}=    Evaluate    [n for n in $theirs if n['opportunity']['id'] == $opp['id']]
    Should Be Empty    ${theirs_mine}    msg=a student who already applied was reminded

*** Keywords ***
Prepare Phase B
    Open Portal Session
    ${admin}=    Admin Token
    Set Suite Variable    ${admin}    ${admin}
    Probe Or Skip As Not Built    Phase B opportunities    GET    /api/opportunities/    ${admin}
    ${main}=    Make Students    820    6    2076    tag=phaseb
    ${bba}=    Make Students    826    1    2076    department=${DEPT_BBA}    school=business    tag=phaseb
    ${low}=    Make Students    827    1    2076    cgpa=6.00    tag=phaseb
    ${cohort}=    Provision Students    ${main}    ${admin}
    ${c2}=    Provision Students    ${bba}    ${admin}
    ${c3}=    Provision Students    ${low}    ${admin}
    ${cohort}=    Evaluate    {**$cohort, **$c2, **$c3}
    # resumes: 820 backend, 821 mechanical (the contrast), 822-823 and the hidden 825 backend,
    # the ineligible two have resumes so only eligibility can refuse them. 824 has none.
    Upload Resume    ${cohort}[220200820][token]    0
    Upload Resume    ${cohort}[220200821][token]    3
    Upload Resume    ${cohort}[220200822][token]    0
    Upload Resume    ${cohort}[220200823][token]    0
    Upload Resume    ${cohort}[220200825][token]    0
    Upload Resume    ${cohort}[220200826][token]    0
    Upload Resume    ${cohort}[220200827][token]    0
    FOR    ${prn}    IN    220200820    220200821    220200822    220200823    220200825    220200826    220200827
        Set Visibility    ${cohort}[${prn}][token]    all
    END
    Set Suite Variable    ${COHORT}    ${cohort}

*** Settings ***
Documentation     Addendum R1-R5: onboarding, career path, transcript, audited document access,
...               what a company never sees, the outcomes table and its CSV, and /media/ closed.
...               Students use PRN sequences 810-819 (batch 2077).
Resource          ../resources/portal.resource
Suite Setup       Prepare Addendum Cohort
Suite Teardown    Delete All Sessions

*** Variables ***
@{PATHS}          placement    business    higher_studies    entrepreneurship    research
...               family_business    competitive_exams    undecided
@{COMPANY_MUST_NOT_SEE}    career_path    transcript    parsed_cgpa    recomputed_cgpa    confirmed_cgpa
...               personal_email    also_attending_placements    cgpa_review    cgpa_matches_roster
${PHONE}          9876543210

*** Test Cases ***
Onboarding Needs A Phone And A Career Path, Then Completes
    ${s}=    Set Variable    ${COHORT}[220200810]
    ${admin}=    Admin Token
    ${t}=    Set Variable    ${s}[token]
    ${form}=    Get Json    /api/profiles/me/onboarding    ${t}
    Should Be Equal    ${form}[completed]    ${False}
    Should Be Equal    ${form}[dismissed]    ${False}
    Should Be Equal    ${form}[student][prn]    220200810
    Should Be Equal As Integers    ${form}[student][batch]    2077
    ${before}=    Get Json    /api/profiles/admin/stats    ${admin}
    ${r}=    Post Json    /api/profiles/me/onboarding    ${t}    ${{ {"career_path": "placement"} }}    400
    ${r}=    Post Json    /api/profiles/me/onboarding    ${t}    ${{ {"phone": $PHONE} }}    400
    ${r}=    Post Json    /api/profiles/me/onboarding    ${t}    ${{ {"phone": $PHONE, "career_path": "other"} }}    400
    ${r}=    Post Json    /api/profiles/me/onboarding    ${t}
    ...    ${{ {"phone": $PHONE, "career_path": "placement", "personal_email": $s["email"]} }}    400
    ${r}=    Post Json    /api/profiles/me/onboarding    ${t}
    ...    ${{ {"phone": $PHONE, "career_path": "business", "personal_email": "e2e.personal@example.org", "also_attending_placements": True} }}    200
    Should Be Equal    ${r.json()}[completed]    ${True}
    Should Be Equal    ${r.json()}[career_path]    business
    ${me}=    Get Json    /api/profiles/me    ${t}
    Should Be Equal    ${me}[onboarding_completed]    ${True}
    Should Not Be Equal    ${me}[onboarding_completed_at]    ${None}
    ${after}=    Get Json    /api/profiles/admin/stats    ${admin}
    Should Be Equal As Integers    ${after}[onboarding_completed]    ${{ $before["onboarding_completed"] + 1 }}

A Student Can Skip Onboarding
    ${t}=    Set Variable    ${COHORT}[220200811][token]
    ${r}=    Api    POST    /api/profiles/me/onboarding/dismiss    ${t}
    Status Is    ${r}    204
    ${form}=    Get Json    /api/profiles/me/onboarding    ${t}
    Should Be Equal    ${form}[dismissed]    ${True}
    Should Be Equal    ${form}[completed]    ${False}
    ${me}=    Get Json    /api/profiles/me    ${t}    # skipping never locks the student out
    Should Be Equal    ${me}[onboarding_completed]    ${False}

Career Path Accepts The Listed Values And Other Needs Text
    ${t}=    Set Variable    ${COHORT}[220200812][token]
    ${me}=    Get Json    /api/profiles/me    ${t}
    Should Be Equal    ${me}[career_path]    undecided
    Should Be Equal    ${me}[also_attending_placements]    ${False}
    Should Be Equal    ${me}[completion_detail][career_path]    ${False}
    FOR    ${path}    IN    @{PATHS}
        ${r}=    Api    PATCH    /api/profiles/me    ${t}    json=${{ {"career_path": $path} }}
        Status Is    ${r}    200
        Should Be Equal    ${r.json()}[career_path]    ${path}
        ${me}=    Get Json    /api/profiles/me    ${t}
        ${done}=    Evaluate    $path != 'undecided'
        Should Be Equal    ${me}[completion_detail][career_path]    ${done}
    END
    ${r}=    Api    PATCH    /api/profiles/me    ${t}    json=${{ {"career_path": "other", "career_path_detail": "Join the family farm"} }}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[career_path_detail]    Join the family farm
    # 'other' needs text of its own: start from a path that carries none, or the stored text would satisfy it
    ${r}=    Api    PATCH    /api/profiles/me    ${t}    json=${{ {"career_path": "placement"} }}
    Status Is    ${r}    200
    ${blank}=    Set Variable    ${SPACE * 3}
    ${bad_bodies}=    Evaluate    [{"career_path": "other"}, {"career_path": "other", "career_path_detail": $blank}, {"career_path": "astronaut"}]
    FOR    ${bad}    IN    @{bad_bodies}
        ${r}=    Api    PATCH    /api/profiles/me    ${t}    json=${bad}
        Status Is    ${r}    400
    END
    ${r}=    Api    PATCH    /api/profiles/me    ${t}    json=${{ {"career_path": "higher_studies", "career_path_detail": "stale", "also_attending_placements": True} }}
    Status Is    ${r}    200
    Should Be Equal    ${r.json()}[career_path_detail]    ${EMPTY}
    Should Be Equal    ${r.json()}[also_attending_placements]    ${True}

A Clean Transcript Is Accepted With No Review
    ${s}=    Set Variable    ${COHORT}[220200813]
    ${pdf}=    Render Transcript    220200813    ${s}[name]    8.50
    ${r}=    Upload    /api/profiles/me/transcript    ${s}[token]    clean.pdf    ${pdf}
    Status Is    ${r}    201
    ${body}=    Set Variable    ${r.json()}
    Should Be Equal    ${body}[transcript_prn]    220200813
    Should Be Equal As Numbers    ${body}[parsed_cgpa]    8.50
    Should Be Equal As Numbers    ${body}[recomputed_cgpa]    8.50
    Should Be Equal    ${body}[cgpa_matches_roster]    ${True}
    Should Be Equal    ${body}[cgpa_review_status]    not_needed
    Should Be Equal    ${body}[transcript_url]    /api/profiles/me/transcript/file
    ${r}=    Api    GET    /api/profiles/me/transcript/file    ${s}[token]
    Status Is    ${r}    200

Someone Else's Transcript Is Refused And Not Stored
    ${s}=    Set Variable    ${COHORT}[220200815]
    ${before}=    Audit Count    transcript_prn_mismatch    220200815
    ${pdf}=    Render Transcript    220200816    E2E Student 816    8.50
    ${r}=    Upload    /api/profiles/me/transcript    ${s}[token]    theirs.pdf    ${pdf}
    Status Is    ${r}    400
    Should Be Equal    ${r.json()}[reason]    prn_mismatch
    Audit Count Should Grow By    ${before}    1    transcript_prn_mismatch    220200815
    ${r}=    Api    GET    /api/profiles/me/transcript/file    ${s}[token]
    Status Is    ${r}    404
    ${me}=    Get Json    /api/profiles/me    ${s}[token]
    Should Be Equal    ${me}[transcript_filename]    ${EMPTY}
    ${r}=    Upload    /api/profiles/me/transcript    ${s}[token]    notes.txt    ${{ b"Cumulative GPA: 9.9" }}
    Status Is    ${r}    400
    ${r}=    Api    POST    /api/profiles/me/transcript    ${s}[token]    data=${{ {} }}
    Status Is    ${r}    400

A Tampered CGPA Is Flagged And The Admin Resolves The Review
    ${s}=    Set Variable    ${COHORT}[220200814]
    ${admin}=    Admin Token
    ${flagged}=    Audit Count    cgpa_mismatch_flagged
    ${pdf}=    Render Transcript    220200814    ${s}[name]    9.40
    ${r}=    Upload    /api/profiles/me/transcript    ${s}[token]    tampered.pdf    ${pdf}
    Status Is    ${r}    201
    Should Be Equal As Numbers    ${r.json()}[parsed_cgpa]    9.40
    Should Be Equal As Numbers    ${r.json()}[recomputed_cgpa]    8.50
    Should Be Equal    ${r.json()}[cgpa_review_status]    open
    Audit Count Should Grow By    ${flagged}    1    cgpa_mismatch_flagged
    ${detail}=    Get Json    /api/profiles/admin/${s}[student_id]    ${admin}
    Should Be Equal    ${detail}[cgpa_review_status]    open
    Should Be Equal As Numbers    ${detail}[student][cgpa]    8.50    msg=the roster CGPA changed
    ${target}=    Set Variable    /api/profiles/admin/${s}[student_id]/cgpa-review
    ${r}=    Api    POST    ${target}    ${s}[token]    json=${{ {"status": "resolved"} }}
    Status Is    ${r}    403
    ${resolved}=    Audit Count    cgpa_review_resolved    220200814
    ${r}=    Api    POST    ${target}    ${admin}    json=${{ {"status": "resolved", "note": "Checked the paper copy."} }}
    Status Is    ${r}    200
    ${detail}=    Get Json    /api/profiles/admin/${s}[student_id]    ${admin}
    Should Be Equal    ${detail}[cgpa_review_status]    resolved
    Audit Count Should Grow By    ${resolved}    1    cgpa_review_resolved    220200814

A Student Confirming Their CGPA Never Touches The Roster
    ${s}=    Set Variable    ${COHORT}[220200814]
    ${r}=    Api    POST    /api/profiles/me/confirm-cgpa    ${s}[token]    json=${{ {"cgpa": "8.40"} }}
    Status Is    ${r}    200
    ${me}=    Get Json    /api/profiles/me    ${s}[token]
    Should Be Equal As Numbers    ${me}[confirmed_cgpa]    8.40
    Should Be Equal As Numbers    ${me}[parsed_cgpa]    9.40
    Should Be Equal As Numbers    ${me}[student][cgpa]    8.50
    FOR    ${bad}    IN    10.5    -1    abc    ${EMPTY}
        ${r}=    Api    POST    /api/profiles/me/confirm-cgpa    ${s}[token]    json=${{ {"cgpa": $bad} }}
        Status Is    ${r}    400
    END
    ${resume}=    Upload Resume    ${s}[token]
    ${me}=    Get Json    /api/profiles/me    ${s}[token]
    Should Be Equal As Numbers    ${me}[confirmed_cgpa]    8.40    msg=a resume upload changed a CGPA field
    Should Be Equal As Numbers    ${me}[parsed_cgpa]    9.40

The Admin Opens The Resume And Transcript And Each Open Is Audited
    ${s}=    Set Variable    ${COHORT}[220200813]
    ${admin}=    Admin Token
    ${sid}=    Set Variable    ${s}[student_id]
    Upload Resume    ${s}[token]
    ${detail}=    Get Json    /api/profiles/admin/${sid}    ${admin}
    Should Be Equal    ${detail}[resume_url]    /api/profiles/admin/${sid}/resume
    Should Be Equal    ${detail}[transcript_url]    /api/profiles/admin/${sid}/transcript
    ${before}=    Audit Count    document_accessed    220200813
    ${r}=    Api    GET    /api/profiles/admin/${sid}/resume    ${admin}
    Status Is    ${r}    200
    Should Start With    ${r.text}    %PDF-
    Should Contain    ${r.headers}[Content-Disposition]    aarav_mehta_backend.pdf
    Audit Count Should Grow By    ${before}    1    document_accessed    220200813
    ${r}=    Api    GET    /api/profiles/admin/${sid}/transcript    ${admin}
    Status Is    ${r}    200
    Should Start With    ${r.text}    %PDF-
    Audit Count Should Grow By    ${before}    2    document_accessed    220200813
    ${r}=    Api    GET    /api/profiles/admin/${sid}/transcript
    Status Is    ${r}    401
    ${r}=    Api    GET    /api/profiles/admin/${sid}/transcript    ${s}[token]
    Status Is    ${r}    403

A Company Never Gets A Transcript, Career Path Or CGPA Field
    ${s}=    Set Variable    ${COHORT}[220200813]
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    ${sid}=    Set Variable    ${s}[student_id]
    ${r}=    Post Json    /api/profiles/admin/${sid}/verification    ${admin}    ${{ {"is_verified": True} }}
    Set Visibility    ${s}[token]    all
    ${r}=    Api    GET    /api/profiles/students/${sid}/transcript    ${acme}
    Status Is    ${r}    404    # even for a visible, verified profile
    ${detail}=    Get Json    /api/profiles/students/${sid}    ${acme}
    ${listed}=    Get Json    /api/profiles/students?prn=220200813    ${acme}
    Should Be Equal As Integers    ${listed}[count]    1
    FOR    ${doc}    IN    ${detail}    ${listed}
        ${leaked}=    Keys Starting With    ${doc}    @{COMPANY_MUST_NOT_SEE}
        Should Be Empty    ${leaked}    msg=a company payload carries ${leaked}
    END
    ${before}=    Set Variable    ${detail}[completion_percent]
    ${r}=    Api    PATCH    /api/profiles/me    ${s}[token]    json=${{ {"career_path": "entrepreneurship"} }}
    Status Is    ${r}    200
    ${after}=    Get Json    /api/profiles/students/${sid}    ${acme}
    Should Be Equal    ${after}[completion_percent]    ${before}    msg=a company can see a career path change in the completion figure
    ${opens}=    Audit Count    document_accessed
    ${r}=    Api    GET    /api/profiles/students/${sid}/resume    ${acme}
    Status Is    ${r}    200
    Audit Count Should Grow By    ${opens}    1    document_accessed

The Outcomes Table Adds Up To The Cohort And The CSV Matches
    ${admin}=    Admin Token
    ${expected}=    Create Dictionary
    ${attending}=    Set Variable    ${0}
    FOR    ${prn}    ${s}    IN    &{COHORT}
        ${me}=    Get Json    /api/profiles/me    ${s}[token]
        ${n}=    Get From Dictionary    ${expected}    ${me}[career_path]    ${0}
        Set To Dictionary    ${expected}    ${me}[career_path]=${n + 1}
        IF    ${me}[also_attending_placements]
            ${attending}=    Evaluate    ${attending} + 1
        END
    END
    ${out}=    Get Json    /api/profiles/admin/outcomes?batch=2077    ${admin}
    Should Be Equal As Integers    ${out}[grand_total]    10
    Should Be Equal As Integers    ${out}[batch]    2077
    ${path_keys}=    Evaluate    [p["value"] for p in $out["paths"]]
    Should Be Equal As Integers    ${{ sum($out["totals"].values()) }}    ${out}[grand_total]
    FOR    ${row}    IN    @{out}[rows]
        Should Be Equal As Integers    ${{ sum($row["counts"].values()) }}    ${row}[total]
        Should Be Equal    ${{ sorted($row["counts"]) }}    ${{ sorted($path_keys) }}    msg=counts must carry every path key, zeros included
    END
    Should Be Equal As Integers    ${{ sum(r["total"] for r in $out["rows"]) }}    10
    FOR    ${path}    ${count}    IN    &{expected}
        ${got}=    Get From Dictionary    ${out}[totals]    ${path}
        Should Be Equal As Integers    ${got}    ${count}    msg=totals[${path}]
    END
    Should Be Equal As Integers    ${out}[also_attending_placements]    ${attending}
    Should Be Equal As Integers    ${out}[verified]    1
    ${everyone}=    Get Json    /api/profiles/admin/outcomes    ${admin}
    Should Be True    ${everyone}[grand_total] >= 10
    ${r}=    Api    GET    /api/profiles/admin/outcomes?batch=abc    ${admin}
    Status Is    ${r}    400
    ${r}=    Api    GET    /api/profiles/admin/outcomes?batch=2077    ${COHORT}[220200810][token]
    Status Is    ${r}    403
    ${r}=    Api    GET    /api/profiles/admin/outcomes?batch=2077    ${{ None }}
    Status Is    ${r}    401
    # the CSV export of the same batch
    ${r}=    Api    GET    /api/profiles/admin/outcomes/export?batch=2077    ${admin}
    Status Is    ${r}    200
    Should Contain    ${r.headers}[Content-Type]    text/csv
    Should Contain    ${r.headers}[Content-Disposition]    attachment
    ${rows}=    Parse Csv    ${r.text}
    Should Be Equal    ${rows}[0]    ${{ ["school"] + $path_keys + ["total"] }}
    Should Be Equal    ${rows}[-1][0]    total
    Should Be Equal As Integers    ${rows}[-1][-1]    10
    Length Should Be    ${rows}    ${{ len($out["rows"]) + 2 }}
    ${acme}=    Acme Token
    ${r}=    Api    GET    /api/profiles/admin/outcomes/export?batch=2077    ${acme}
    Status Is    ${r}    403

/media/ Is Closed
    ${files}=    Stored Files    **/*.pdf
    Should Not Be Empty    ${files}    msg=no stored document to test against: the 404s below would prove nothing
    FOR    ${rel}    IN    @{files}
        ${r}=    Api    GET    /media/${rel}
        Status Is    ${r}    404
    END
    ${r}=    Api    GET    /media/
    Status Is    ${r}    404

*** Keywords ***
Prepare Addendum Cohort
    Open Portal Session
    ${admin}=    Admin Token
    ${students}=    Make Students    810    10    2077    tag=addendum
    ${cohort}=    Provision Students    ${students}    ${admin}
    Set Suite Variable    ${COHORT}    ${cohort}

*** Settings ***
Documentation     Stage 4: the recruiter's shortlist, the CV zip and the password-protected contact zip
...               (docs/OPPORTUNITIES_API_CONTRACT.md). Students use PRN sequences 870-879 (batch 2073).
...               Probe route: GET /api/profiles/students/shortlist/resumes.
Resource          ../resources/opportunities.resource
Suite Setup       Prepare Exports
Suite Teardown    Delete All Sessions

*** Variables ***
${CV_URL}         /api/profiles/students/shortlist/resumes
${CONTACTS_URL}   /api/profiles/students/shortlist/contacts
${CONTACT_HEADER}    prn,full_name,department,programme,batch,cgpa,email,phone,contact_available,shortlisted_on

*** Test Cases ***
The Shortlisted Filter Returns The Real Shortlist Only
    ${rows}=    All Pages    /api/profiles/students?shortlisted=true    ${ACME}
    ${prns}=    Evaluate    {r['prn'] for r in $rows} & {p for p in $COHORT}
    Should Be Equal    ${prns}    ${{ {"220200870", "220200871", "220200872", "220200873", "220200874"} }}
    FOR    ${row}    IN    @{rows}
        Should Be True    ${row}[is_shortlisted]
    END
    ${all}=    All Pages    /api/profiles/students?search=E2E    ${ACME}
    ${flag}=    Evaluate    {r['prn']: r['is_shortlisted'] for r in $all if r['prn'] in $COHORT}
    Should Be Equal    ${flag}[220200875]    ${False}    msg=an unshortlisted visible student is flagged as shortlisted
    ${theirs}=    All Pages    /api/profiles/students?shortlisted=true    ${NIMBUS}
    ${prns}=    Evaluate    {r['prn'] for r in $theirs} & {p for p in $COHORT}
    Should Be Equal    ${prns}    ${{ {"220200876"} }}
    ${r}=    Api    GET    /api/profiles/students?shortlisted=maybe    ${ACME}
    Status Is    ${r}    400

The CV Zip Counts Students With No Resume
    ${before}=    Audit Count    documents_bulk_downloaded
    ${r}=    Api    GET    ${CV_URL}    ${ACME}
    Status Is    ${r}    200
    Should Contain    ${r.headers}[Content-Type]    zip
    Should Be Equal As Integers    ${r.headers}[X-Skipped-Without-Resume]    1
    ${names}=    Zip Names    ${r.content}
    FOR    ${seq}    IN    870    871    873    874
        ${hit}=    Evaluate    [n for n in $names if n.startswith('220200${seq}-') and n.endswith('.pdf')]
        Length Should Be    ${hit}    1    msg=220200${seq} is missing from the CV zip: ${names}
    END
    ${none}=    Evaluate    [n for n in $names if n.startswith('220200872-')]
    Should Be Empty    ${none}    msg=a student with no resume has a file in the zip
    Should Contain    ${names}    SKIPPED.txt
    ${skipped}=    Bytes To Text    ${{ __import__('zipfile').ZipFile(__import__('io').BytesIO($r.content)).read('SKIPPED.txt') }}
    Should Contain    ${skipped}    220200872
    ${original_name}    ${original}=    Sample Resume    0
    ${member}=    Evaluate    [n for n in $names if n.startswith('220200870-')][0]
    ${bytes}=    Zip Member    ${r.content}    ${member}
    Should Be True    $bytes == $original    msg=the zipped resume is not the student's current resume
    Audit Count Should Grow By    ${before}    1    documents_bulk_downloaded

The Contact Zip Needs The Password And Holds The Right Rows
    ${before}=    Audit Count    shortlist_exported
    ${r}=    Api    POST    ${CONTACTS_URL}    ${ACME}
    Status Is    ${r}    200
    ${body}=    Set Variable    ${r.json()}
    FOR    ${key}    IN    password    filename    zip_base64    row_count
        Dictionary Should Contain Key    ${body}    ${key}
    END
    Should Be True    len($body['password']) >= 16
    ${zip}=    Decode Base64    ${body}[zip_base64]
    ${refused}=    Aes Zip Refuses Without Password    ${zip}
    Should Be True    ${refused}    msg=the contact zip opened without the right password
    ${aes}=    Aes Zip Is Aes256    ${zip}
    Should Be True    ${aes}    msg=the contact zip is not AES-256
    ${members}=    Read Aes Zip    ${zip}    ${body}[password]
    Should Be Equal    ${{ sorted($members) }}    ${{ ["contacts.csv"] }}
    ${password_bytes}=    Evaluate    $body['password'].encode()
    FOR    ${name}    ${content}    IN    &{members}
        Should Not Contain    ${content}    ${password_bytes}    msg=the password is written inside the archive
    END
    ${csv}=    Parse Csv    ${{ $members['contacts.csv'].decode() }}
    Should Be Equal    ${{ ",".join($csv[0]) }}    ${CONTACT_HEADER}
    ${rows}=    Evaluate    {r[0]: r for r in $csv[1:]}
    ${mine}=    Evaluate    {p for p in $rows if p in $COHORT}
    Should Be Equal    ${mine}    ${{ {"220200870", "220200871", "220200872", "220200873", "220200874"} }}
    Should Be Equal As Integers    ${body}[row_count]    ${{ len($csv) - 1 }}
    # verified students carry their contact details; the unverified one has a blank row
    ${verified}=    Set Variable    ${rows}[220200870]
    Should Be Equal    ${verified}[6]    ${COHORT}[220200870][email]
    Should Be Equal    ${{ $verified[8].lower() }}    true
    ${unverified}=    Set Variable    ${rows}[220200873]
    Should Be Empty    ${unverified}[6]
    Should Be Empty    ${unverified}[7]
    Should Be Equal    ${{ $unverified[8].lower() }}    false
    Audit Count Should Grow By    ${before}    1    shortlist_exported
    ${again}=    Api    POST    ${CONTACTS_URL}    ${ACME}
    Status Is    ${again}    200
    Should Not Be Equal    ${again.json()}[password]    ${body}[password]    msg=the password repeated

A Student Who Goes Hidden After Being Shortlisted Is In Neither Export
    Set Visibility    ${COHORT}[220200874][token]    hidden
    ${rows}=    All Pages    /api/profiles/students?shortlisted=true    ${ACME}
    ${prns}=    Evaluate    {r['prn'] for r in $rows}
    Should Not Contain    ${prns}    220200874
    ${cv}=    Api    GET    ${CV_URL}    ${ACME}
    Status Is    ${cv}    200
    ${names}=    Zip Names    ${cv.content}
    ${gone}=    Evaluate    [n for n in $names if n.startswith('220200874-')]
    Should Be Empty    ${gone}    msg=a hidden student's resume is still in the CV zip
    ${r}=    Api    POST    ${CONTACTS_URL}    ${ACME}
    Status Is    ${r}    200
    ${members}=    Read Aes Zip    ${{ __import__('base64').b64decode($r.json()['zip_base64']) }}    ${r.json()}[password]
    ${csv}=    Parse Csv    ${{ $members['contacts.csv'].decode() }}
    ${prns}=    Evaluate    {row[0] for row in $csv[1:]}
    Should Not Contain    ${prns}    220200874
    Should Contain    ${prns}    220200870

One Company Cannot Export Another Company's Shortlist
    ${r}=    Api    POST    ${CONTACTS_URL}    ${NIMBUS}
    Status Is    ${r}    200
    ${members}=    Read Aes Zip    ${{ __import__('base64').b64decode($r.json()['zip_base64']) }}    ${r.json()}[password]
    ${csv}=    Parse Csv    ${{ $members['contacts.csv'].decode() }}
    ${prns}=    Evaluate    {row[0] for row in $csv[1:]} & {p for p in $COHORT}
    Should Be Equal    ${prns}    ${{ {"220200876"} }}
    ${cv}=    Api    GET    ${CV_URL}    ${NIMBUS}
    Status Is    ${cv}    200
    ${names}=    Zip Names    ${cv.content}
    ${acme_only}=    Evaluate    [n for n in $names if n[:9] in ('220200870', '220200871', '220200873')]
    Should Be Empty    ${acme_only}

Only A Recruiter Can Export
    FOR    ${token}    IN    ${COHORT}[220200870][token]    ${ADMIN}
        ${r}=    Api    GET    ${CV_URL}    ${token}
        Status Is    ${r}    403
        ${r}=    Api    POST    ${CONTACTS_URL}    ${token}
        Status Is    ${r}    403
    END
    ${r}=    Api    GET    ${CV_URL}
    Status Is    ${r}    401
    ${r}=    Api    POST    ${CONTACTS_URL}
    Status Is    ${r}    401

An Application At Shortlisted Status Counts As A Pick, An Applied One Does Not
    ${cid}=    Company Id Of    ${ACME}
    ${opp}=    Admin Creates Open Opportunity    ${ADMIN}    ${cid}    title=Export Journey
    ${picked}=    Apply    ${COHORT}[220200877][token]    ${opp}[id]
    Status Is    ${picked}    201
    ${waiting}=    Apply    ${COHORT}[220200878][token]    ${opp}[id]
    Status Is    ${waiting}    201
    ${rows}=    All Pages    /api/profiles/students?shortlisted=true    ${ACME}
    ${prns}=    Evaluate    {r['prn'] for r in $rows}
    Should Not Contain    ${prns}    220200877    msg=an application alone is not a pick
    Set Application Status    ${ACME}    ${picked.json()}[id]    shortlisted
    ${rows}=    All Pages    /api/profiles/students?shortlisted=true    ${ACME}
    ${prns}=    Evaluate    {r['prn'] for r in $rows}
    Should Contain    ${prns}    220200877
    Should Not Contain    ${prns}    220200878

*** Keywords ***
Prepare Exports
    Open Portal Session
    ${admin}=    Admin Token
    ${acme}=    Acme Token
    Probe Or Skip As Not Built    shortlist exports    GET    ${CV_URL}    ${acme}
    Set Suite Variable    ${ADMIN}    ${admin}
    Set Suite Variable    ${ACME}    ${acme}
    ${nimbus}=    Nimbus Token
    Set Suite Variable    ${NIMBUS}    ${nimbus}
    ${students}=    Make Students    870    9    2073    tag=exports
    ${cohort}=    Provision Students    ${students}    ${admin}
    Set Suite Variable    ${COHORT}    ${cohort}
    # resumes for everyone but 872; visibility "all" for everyone
    FOR    ${seq}    IN    870    871    873    874    875    876    877    878
        Upload Resume    ${cohort}[220200${seq}][token]    0
    END
    FOR    ${seq}    IN    870    871    872    873    874    875    876    877    878
        Set Visibility    ${cohort}[220200${seq}][token]    all
    END
    # verified: all but 873 (the unverified one)
    FOR    ${seq}    IN    870    871    872    874    875    876    877    878
        Post Json    /api/profiles/admin/${cohort}[220200${seq}][student_id]/verification    ${admin}    ${{ {"is_verified": True} }}
    END
    # Acme's picks: 870-874. Nimbus's: 876.
    FOR    ${seq}    IN    870    871    872    873    874
        Post Json    /api/profiles/students/${cohort}[220200${seq}][student_id]/shortlist    ${acme}    ${{ {"note": "e2e"} }}    201
    END
    Post Json    /api/profiles/students/${cohort}[220200876][student_id]/shortlist    ${nimbus}    ${{ {"note": "e2e"} }}    201

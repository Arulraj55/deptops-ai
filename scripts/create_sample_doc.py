"""
Creates a sample academic regulation document for testing the Knowledge Agent.
Usage: python scripts/create_sample_doc.py
"""

from pathlib import Path

CONTENT = """
ACADEMIC REGULATIONS AND POLICIES
Department of Computer Science
Academic Year 2024-2025

1. ATTENDANCE POLICY
   1.1 Students must maintain a minimum attendance of 75% in each subject.
   1.2 Students with attendance below 75% are not eligible to appear in end-semester examinations.
   1.3 Medical leave of up to 10 days per semester may be granted on submission of a valid medical certificate.
   1.4 Attendance is calculated separately for theory and laboratory courses.

2. EXAMINATION RULES
   2.1 End-semester examinations carry 70 marks. Internal assessment carries 30 marks.
   2.2 Students must score a minimum of 50% (35/70) in end-semester exams to pass.
   2.3 A student scoring below 40 marks in any subject is considered to have failed that subject.
   2.4 Supplementary examinations are conducted within 30 days of result declaration.
   2.5 Students may apply for revaluation within 15 days of result publication by paying the prescribed fee.

3. GRADING SYSTEM
   O (Outstanding): 91-100 marks, 10 grade points
   A+ (Excellent):  81-90 marks, 9 grade points
   A  (Very Good):  71-80 marks, 8 grade points
   B+ (Good):       61-70 marks, 7 grade points
   B  (Average):    51-60 marks, 6 grade points
   C  (Satisfactory): 41-50 marks, 5 grade points
   U  (Unsatisfactory): Below 40 marks, 0 grade points — Fail

4. PROMOTION RULES
   4.1 Students must pass all subjects in a semester to be promoted to the next year.
   4.2 Students with arrears (failed subjects) may carry them to the next semester.
   4.3 Maximum duration to complete the programme: 6 years (for a 4-year programme).

5. PLACEMENT ELIGIBILITY
   5.1 Students must have a minimum CGPA of 6.0 to be eligible for campus placements.
   5.2 No active backlogs (failed subjects) at the time of placement drive.
   5.3 Students must register with the Training & Placement Cell before the end of the 5th semester.
   5.4 Students with more than 2 arrears are not eligible for off-campus placement support.

6. LEAVE POLICY
   6.1 Students may apply for on-duty (OD) leave for participating in technical events, sports, or NSS/NCC activities.
   6.2 OD leave does not count toward absence but must be approved by the HOD in advance.
   6.3 Medical leave applications must be submitted within 3 days of returning to college.

7. CONDUCT AND DISCIPLINE
   7.1 Use of mobile phones is prohibited inside classrooms and laboratories.
   7.2 Ragging in any form is a punishable offence and may result in expulsion.
   7.3 Academic dishonesty (copying, plagiarism) during examinations leads to cancellation of the paper.

8. COURSE STRUCTURE
   8.1 Each semester consists of 5-6 theory subjects and 1-2 laboratory courses.
   8.2 Each theory subject carries 4 credits; laboratory courses carry 1-2 credits.
   8.3 Total credits required for graduation: 160 credits.
   8.4 Students must complete a project work of 6 credits in their final year.

9. FEE STRUCTURE
   9.1 Tuition fee: Rs. 75,000 per year.
   9.2 Laboratory fee: Rs. 5,000 per year.
   9.3 Examination fee: Rs. 500 per subject.
   9.4 Fee concession is available for students from economically weaker sections on submission of income certificate.

10. GRIEVANCE REDRESSAL
    10.1 Students may raise academic grievances through the department grievance committee.
    10.2 Grievances must be submitted in writing within 7 days of the issue.
    10.3 The committee will resolve grievances within 15 working days.
"""

output_path = Path("data/documents/academic_regulations.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(CONTENT.strip(), encoding="utf-8")
print(f"[✓] Sample document created: {output_path.resolve()}")

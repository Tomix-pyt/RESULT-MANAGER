"""Every word printed on the result sheet, copied from score_sheet_template.xlsx.
Spelling is kept EXACTLY as in the template (including its typos) so the printout matches your sheet.
To correct a word, change it here, once."""

SCHOOL_DEFAULTS = {
    "school_name": "CREATIVITY SCIENCE AND TECHNICAL COLLEGE, WANNUNE",
    "school_region": "BENUE STATE, NIGERIA.",
    "school_address": "Behind New Timber Shed Wannune, Tarka L.G.A, Benue state.",
    "principal_name": "Kwagh Joseph",
}

BAR_INFO = "STUDENT'S INFORMATION"
BAR_TERMINAL = "STUDENT'S TERMINAL CONTINUOUS ASSESSMENT PERFOMANCE BREAKDOWN"
BAR_ANNUAL = "STUDENT'S ANNUAL CONTINUOUS ASSESSMENT PERFOMANCE BREAKDOWN"
BAR_REMARKS = "TEACHER'S REMARKS"

# columns of the subjects table, in order
SUBJECT_HEAD = "SUBJECTS"
SCORE_COLUMNS = ["1'st CA", "2'nd CA", "3'rd CA", "Exams"]          # report_slot 1..4
RESULT_COLUMNS = ["Total", "Highest in Class", "Lowest in Class", "Position in Class", "Grade", "Remark"]
ANNUAL_COLUMNS = ["1st Term", "2nd Term", "3rd Term", "Total", "Average", "Highest in Class",
                  "Lowest in Class", "Position in Class", "Grade", "Remark"]
# Printed when the school has not defined a grading scale yet (copied from the template, typos included)
GRADING_KEY_FALLBACK = ('Grading keys: ("A"- Distinction(75 and above) "B"- Ver Good(55-64) "C"- Good(40-54) '
                        '"D"-Fail(39 and above "E"-"Poor)')

AFFECTIVE_TITLE = "AFFECTIVE DEVELOPMENT"
RATING_SCALE_TITLE = "RATING SCALE"
AFFECTIVE = [("attentiveness", "Attentiveness"), ("attendance", "Attendance"), ("punctuality", "Punctuality"),
             ("neatness", "Neatness"), ("politeness", "Politeness"), ("self_control", "Self control"),
             ("curiosity", "Curiosity"), ("honesty", "Honesty"), ("tolerance", "Tolerance"),
             ("leadership", "Leadership"), ("courage", "Courage")]
PSYCHOMOTOR_TITLE = "PSHYCHOMOTOR      SKILLS"
PSYCHOMOTOR = [("handwriting", "H.Writting"), ("fluency", "Fluency"), ("gymnastics", "Gymnastics"),
               ("music", "Mus. skills"), ("games", "Gam./Spts")]
RATING_KEY = [(5, "Excellent"), (4, "V.Good"), (3, "Good"), (2, "Fair"), (1, "Poor")]
TRAIT_KEYS = [k for k, _ in AFFECTIVE] + [k for k, _ in PSYCHOMOTOR]

LABEL_TOTAL_OBTAINABLE = "Total obtainable  Marks:"
LABEL_TOTAL_OBTAINED = "Total Marks obtained:"
LABEL_TOT_IN_CLASS = "Tot. in class:"
LABEL_AVERAGE = "Average:"
LABEL_POSITION = "Postion:"

REMARK_FORM = "Form Teacher's Remarks:"
REMARK_PRINCIPAL = "Principal's Remarks:"

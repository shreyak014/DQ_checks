-- This query finds the student(s) who scored the highest marks in Chemistry in the 10th class.
-- It handles cases where multiple students may have the same highest score.

SELECT
    student_id,
    student_name,
    class,
    subject,
    marks
FROM
    student_marks
WHERE
    class = '10th'
    AND subject = 'Chemistry'
    AND marks = (
        -- Subquery to find the maximum marks in Chemistry for the 10th class
        SELECT MAX(marks)
        FROM student_marks
        WHERE class = '10th' AND subject = 'Chemistry'
    );

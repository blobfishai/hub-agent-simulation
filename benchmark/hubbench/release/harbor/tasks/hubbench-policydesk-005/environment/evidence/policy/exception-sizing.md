# Exception sizing rule (extract)

An exception entry covers exactly the blocked-but-recoverable requests it is raised for. It is never widened to admit a refused segregation-of-duties conflict, and its covered count never exceeds the signed approval's maximum.

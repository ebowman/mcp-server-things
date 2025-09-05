tell application "Things3"
    -- Try to get todos with due dates
    set dueHits to (count of (to dos whose status is open and due date is not missing value))
    
    -- Try to get todos with activation dates  
    set whenHits to (count of (to dos whose status is open and activation date is not missing value))
    
    return "Todos with due dates: " & dueHits & ", Todos with activation dates: " & whenHits
end tell
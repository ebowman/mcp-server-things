"""AppleScript query builders for Things 3 data retrieval."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AppleScriptQueries:
    """Builds AppleScript queries for retrieving Things 3 data."""

    def build_get_todos_script(self, project_uuid: Optional[str] = None) -> str:
        """Build AppleScript to get todos, optionally filtered by project.

        Args:
            project_uuid: Optional project UUID to filter by

        Returns:
            AppleScript code as string
        """
        if project_uuid:
            return f'''
            on replaceText(someText, oldText, newText)
                set AppleScript's text item delimiters to oldText
                set textItems to text items of someText
                set AppleScript's text item delimiters to newText
                set newText to textItems as string
                set AppleScript's text item delimiters to {{}}
                return newText
            end replaceText

            tell application "Things3"
                set theProject to project id "{project_uuid}"
                set todoSource to to dos of theProject

                -- Check if there are any todos
                if length of todoSource = 0 then
                    return ""
                end if

                -- Optimized: Build output directly without intermediate arrays
                set outputText to ""
                repeat with theTodo in todoSource
                    if outputText is not "" then
                        set outputText to outputText & ", "
                    end if

                    -- Handle date conversion properly
                    set creationDateStr to ""
                    try
                        set creationDateStr to ((creation date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set creationDateStr to my replaceText(creationDateStr, ":", "§COLON§")
                    on error
                        set creationDateStr to "missing value"
                    end try

                    set modificationDateStr to ""
                    try
                        set modificationDateStr to ((modification date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set modificationDateStr to my replaceText(modificationDateStr, ":", "§COLON§")
                    on error
                        set modificationDateStr to "missing value"
                    end try

                    -- Handle notes which might contain commas
                    set noteStr to ""
                    try
                        set noteStr to (notes of theTodo)
                        -- Replace commas in notes to avoid parsing issues
                        set noteStr to my replaceText(noteStr, ",", "§COMMA§")
                    on error
                        set noteStr to "missing value"
                    end try

                    -- Handle activation date extraction with time components for reminder detection
                    set activationDateStr to ""
                    try
                        set activationDateStr to ((activation date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set activationDateStr to my replaceText(activationDateStr, ":", "§COLON§")
                    on error
                        set activationDateStr to "missing value"
                    end try

                    -- Handle due date
                    set dueDateStr to ""
                    try
                        set dueDateStr to ((due date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set dueDateStr to my replaceText(dueDateStr, ":", "§COLON§")
                    on error
                        set dueDateStr to "missing value"
                    end try

                    set outputText to outputText & "id:" & (id of theTodo) & ", name:" & (name of theTodo) & ", notes:" & noteStr & ", status:" & (status of theTodo) & ", creation_date:" & creationDateStr & ", modification_date:" & modificationDateStr & ", activation_date:" & activationDateStr & ", due_date:" & dueDateStr
                end repeat

                return outputText
            end tell
            '''
        else:
            return '''
            on replaceText(someText, oldText, newText)
                set AppleScript's text item delimiters to oldText
                set textItems to text items of someText
                set AppleScript's text item delimiters to newText
                set newText to textItems as string
                set AppleScript's text item delimiters to {}
                return newText
            end replaceText

            tell application "Things3"
                set todoSource to to dos

                -- Check if there are any todos
                if length of todoSource = 0 then
                    return ""
                end if

                -- Optimized: Build output directly without intermediate arrays
                set outputText to ""
                repeat with theTodo in todoSource
                    if outputText is not "" then
                        set outputText to outputText & ", "
                    end if

                    -- Handle date conversion properly
                    set creationDateStr to ""
                    try
                        set creationDateStr to ((creation date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set creationDateStr to my replaceText(creationDateStr, ":", "§COLON§")
                    on error
                        set creationDateStr to "missing value"
                    end try

                    set modificationDateStr to ""
                    try
                        set modificationDateStr to ((modification date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set modificationDateStr to my replaceText(modificationDateStr, ":", "§COLON§")
                    on error
                        set modificationDateStr to "missing value"
                    end try

                    -- Handle notes which might contain commas
                    set noteStr to ""
                    try
                        set noteStr to (notes of theTodo)
                        -- Replace commas in notes to avoid parsing issues
                        set noteStr to my replaceText(noteStr, ",", "§COMMA§")
                    on error
                        set noteStr to "missing value"
                    end try

                    -- Handle activation date extraction with time components for reminder detection
                    set activationDateStr to ""
                    try
                        set activationDateStr to ((activation date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set activationDateStr to my replaceText(activationDateStr, ":", "§COLON§")
                    on error
                        set activationDateStr to "missing value"
                    end try

                    -- Handle due date
                    set dueDateStr to ""
                    try
                        set dueDateStr to ((due date of theTodo) as string)
                        -- Escape colons in dates to avoid parsing issues
                        set dueDateStr to my replaceText(dueDateStr, ":", "§COLON§")
                    on error
                        set dueDateStr to "missing value"
                    end try

                    set outputText to outputText & "id:" & (id of theTodo) & ", name:" & (name of theTodo) & ", notes:" & noteStr & ", status:" & (status of theTodo) & ", creation_date:" & creationDateStr & ", modification_date:" & modificationDateStr & ", activation_date:" & activationDateStr & ", due_date:" & dueDateStr
                end repeat

                return outputText
            end tell
            '''

    def build_get_projects_script(self) -> str:
        """Build AppleScript to get all projects.

        Returns:
            AppleScript code as string
        """
        return '''
        on replaceText(someText, oldText, newText)
            set AppleScript's text item delimiters to oldText
            set textItems to text items of someText
            set AppleScript's text item delimiters to newText
            set newText to textItems as string
            set AppleScript's text item delimiters to {}
            return newText
        end replaceText

        tell application "Things3"
            set projectSource to projects

            -- Check if there are any projects
            if length of projectSource = 0 then
                return ""
            end if

            -- Optimized: Build output directly without intermediate arrays
            set outputText to ""
            repeat with theProject in projectSource
                if outputText is not "" then
                    set outputText to outputText & ", "
                end if

                -- Handle all date fields that projects inherit from todos
                set creationDateStr to ""
                try
                    set creationDateStr to ((creation date of theProject) as string)
                on error
                    set creationDateStr to "missing value"
                end try

                set modificationDateStr to ""
                try
                    set modificationDateStr to ((modification date of theProject) as string)
                on error
                    set modificationDateStr to "missing value"
                end try

                set dueDateStr to ""
                try
                    set dueDateStr to ((due date of theProject) as string)
                on error
                    set dueDateStr to "missing value"
                end try

                set startDateStr to ""
                try
                    set startDateStr to ((activation date of theProject) as string)
                on error
                    set startDateStr to "missing value"
                end try

                set completionDateStr to ""
                try
                    set completionDateStr to ((completion date of theProject) as string)
                on error
                    set completionDateStr to "missing value"
                end try

                set cancellationDateStr to ""
                try
                    set cancellationDateStr to ((cancellation date of theProject) as string)
                on error
                    set cancellationDateStr to "missing value"
                end try

                -- Handle tag names (projects can have tags)
                set tagNamesStr to ""
                try
                    set tagList to (tag names of theProject)
                    if (count of tagList) > 0 then
                        set AppleScript's text item delimiters to ","
                        set tagNamesStr to (tagList as string)
                        set AppleScript's text item delimiters to {}
                    else
                        set tagNamesStr to ""
                    end if
                on error
                    set tagNamesStr to ""
                end try

                -- Handle contact (projects can have contacts)
                set contactStr to ""
                try
                    set contactStr to ((contact of theProject) as string)
                on error
                    set contactStr to "missing value"
                end try

                -- Handle area (projects can be in areas)
                set areaStr to ""
                try
                    set areaStr to ((area of theProject) as string)
                on error
                    set areaStr to "missing value"
                end try

                -- Handle parent project (projects can be sub-projects)
                set projectStr to ""
                try
                    set projectStr to ((project of theProject) as string)
                on error
                    set projectStr to "missing value"
                end try

                -- Handle notes which might contain commas
                set noteStr to ""
                try
                    set noteStr to (notes of theProject)
                    -- Replace commas in notes to avoid parsing issues
                    set noteStr to my replaceText(noteStr, ",", "§COMMA§")
                on error
                    set noteStr to "missing value"
                end try

                -- Build complete project record with all inherited todo fields
                set outputText to outputText & "id:" & (id of theProject) & ", name:" & (name of theProject) & ", notes:" & noteStr & ", status:" & (status of theProject) & ", tag_names:" & tagNamesStr & ", creation_date:" & creationDateStr & ", modification_date:" & modificationDateStr & ", due_date:" & dueDateStr & ", start_date:" & startDateStr & ", completion_date:" & completionDateStr & ", cancellation_date:" & cancellationDateStr & ", contact:" & contactStr & ", area:" & areaStr & ", project:" & projectStr
            end repeat

            return outputText
        end tell
        '''

    def build_get_areas_script(self) -> str:
        """Build AppleScript to get all areas.

        Returns:
            AppleScript code as string
        """
        return '''
        on replaceText(someText, oldText, newText)
            set AppleScript's text item delimiters to oldText
            set textItems to text items of someText
            set AppleScript's text item delimiters to newText
            set newText to textItems as string
            set AppleScript's text item delimiters to {}
            return newText
        end replaceText

        tell application "Things3"
            set areaSource to areas

            -- Check if there are any areas
            if length of areaSource = 0 then
                return ""
            end if

            -- Optimized: Build output directly without intermediate arrays
            -- Areas in Things 3 only have id and name properties
            set outputText to ""
            repeat with theArea in areaSource
                if outputText is not "" then
                    set outputText to outputText & ", "
                end if

                set outputText to outputText & "id:" & (id of theArea) & ", name:" & (name of theArea)
            end repeat

            return outputText
        end tell
        '''

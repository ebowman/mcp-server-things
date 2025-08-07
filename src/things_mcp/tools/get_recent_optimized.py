"""Optimized get_recent implementation using Things 3 native filtering."""

async def get_recent_optimized(self, period: str) -> List[Dict[str, Any]]:
    """Get recently created items using Things 3's native filtering capabilities.
    
    This implementation uses AppleScript's 'whose' clause to let Things 3
    do the filtering natively, which is MUCH faster than iterating through
    all items manually.
    
    Args:
        period: Time period (e.g., '3d', '1w', '2m', '1y')
        
    Returns:
        List of recent item dictionaries
    """
    try:
        # Parse the period to get number of days
        days = self._parse_period_to_days(period)
        
        # Build highly optimized AppleScript using native filtering
        # This lets Things 3 do the heavy lifting internally
        script = f'''
        tell application "Things3"
            set recentItems to {{}}
            set cutoffDate to (current date) - ({days} * days)
            set maxResults to 200
            
            -- Use native filtering with "whose" clause for todos
            -- This is ORDERS OF MAGNITUDE faster than manual iteration
            try
                -- Get todos created after cutoff date using native filtering
                -- Things 3 handles this internally with its optimized database
                set recentTodos to to dos whose creation date > cutoffDate
                
                -- Limit results for performance
                set todoCount to 0
                repeat with theTodo in recentTodos
                    if todoCount >= maxResults then exit repeat
                    
                    try
                        set itemRecord to {{}}
                        set itemRecord to itemRecord & {{id:(id of theTodo)}}
                        set itemRecord to itemRecord & {{name:(name of theTodo)}}
                        set itemRecord to itemRecord & {{notes:(notes of theTodo)}}
                        set itemRecord to itemRecord & {{status:(status of theTodo)}}
                        set itemRecord to itemRecord & {{tag_names:(tag names of theTodo)}}
                        set itemRecord to itemRecord & {{creation_date:(creation date of theTodo)}}
                        set itemRecord to itemRecord & {{modification_date:(modification date of theTodo)}}
                        set itemRecord to itemRecord & {{item_type:"todo"}}
                        
                        -- Include activation date if scheduled
                        try
                            set itemRecord to itemRecord & {{activation_date:(activation date of theTodo)}}
                        on error
                            set itemRecord to itemRecord & {{activation_date:missing value}}
                        end try
                        
                        -- Include project info if available
                        try
                            set todoProject to project of theTodo
                            if todoProject is not missing value then
                                set itemRecord to itemRecord & {{project_id:(id of todoProject)}}
                                set itemRecord to itemRecord & {{project_name:(name of todoProject)}}
                            end if
                        on error
                            -- No project
                        end try
                        
                        -- Include area info if available
                        try
                            set todoArea to area of theTodo
                            if todoArea is not missing value then
                                set itemRecord to itemRecord & {{area_id:(id of todoArea)}}
                                set itemRecord to itemRecord & {{area_name:(name of todoArea)}}
                            end if
                        on error
                            -- No area
                        end try
                        
                        set recentItems to recentItems & {{itemRecord}}
                        set todoCount to todoCount + 1
                    on error
                        -- Skip items that can't be accessed
                    end try
                end repeat
            on error errMsg
                -- Log but continue if todos filtering fails
                log "Todo filtering error: " & errMsg
            end try
            
            -- Also get recent projects using native filtering
            if (count of recentItems) < maxResults then
                try
                    set recentProjects to projects whose creation date > cutoffDate
                    
                    set projectCount to 0
                    set remainingSlots to maxResults - (count of recentItems)
                    
                    repeat with theProject in recentProjects
                        if projectCount >= remainingSlots then exit repeat
                        
                        try
                            set itemRecord to {{}}
                            set itemRecord to itemRecord & {{id:(id of theProject)}}
                            set itemRecord to itemRecord & {{name:(name of theProject)}}
                            set itemRecord to itemRecord & {{notes:(notes of theProject)}}
                            set itemRecord to itemRecord & {{status:(status of theProject)}}
                            set itemRecord to itemRecord & {{tag_names:(tag names of theProject)}}
                            set itemRecord to itemRecord & {{creation_date:(creation date of theProject)}}
                            set itemRecord to itemRecord & {{modification_date:(modification date of theProject)}}
                            set itemRecord to itemRecord & {{item_type:"project"}}
                            
                            -- Include area info if available
                            try
                                set projectArea to area of theProject
                                if projectArea is not missing value then
                                    set itemRecord to itemRecord & {{area_id:(id of projectArea)}}
                                    set itemRecord to itemRecord & {{area_name:(name of projectArea)}}
                                end if
                            on error
                                -- No area
                            end try
                            
                            set recentItems to recentItems & {{itemRecord}}
                            set projectCount to projectCount + 1
                        on error
                            -- Skip items that can't be accessed
                        end try
                    end repeat
                on error errMsg
                    -- Log but continue if project filtering fails
                    log "Project filtering error: " & errMsg
                end try
            end if
            
            return recentItems
        end tell
        '''
        
        # Don't cache this query as results change frequently
        result = await self.applescript.execute_applescript(script, cache_key=None)
        
        if result.get("success"):
            # Parse the AppleScript output
            raw_records = self.applescript._parse_applescript_list(result.get("output", ""))
            
            # Convert to standardized format
            items = []
            for record in raw_records:
                item_dict = {
                    "id": record.get("id", "unknown"),
                    "uuid": record.get("id", "unknown"),
                    "title": record.get("name", ""),
                    "notes": record.get("notes", ""),
                    "status": record.get("status", "open"),
                    "type": record.get("item_type", "unknown"),
                    "tags": record.get("tag_names", []) if isinstance(record.get("tag_names"), list) else [],
                    "creation_date": record.get("creation_date"),
                    "modification_date": record.get("modification_date"),
                    "activation_date": record.get("activation_date"),
                    "project_id": record.get("project_id"),
                    "project_name": record.get("project_name"),
                    "area_id": record.get("area_id"),
                    "area_name": record.get("area_name")
                }
                items.append(item_dict)
            
            # Sort by creation date (newest first)
            items.sort(key=lambda x: x.get("creation_date", ""), reverse=True)
            
            logger.info(f"Found {len(items)} recent items in period {period}")
            return items
        else:
            logger.error(f"Failed to get recent items: {result.get('error')}")
            return []
    
    except Exception as e:
        logger.error(f"Error in get_recent: {e}")
        raise
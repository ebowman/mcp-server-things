# SPARC Plan: Hybrid things.py Implementation

## 1. SPECIFICATION

### 1.1 Requirements

#### Functional Requirements
- **FR1**: Implement things.py for all read operations with automatic fallback to AppleScript
- **FR2**: Maintain AppleScript for all write operations (add, update, delete, move)
- **FR3**: Preserve exact API compatibility with existing MCP interface
- **FR4**: Support configuration toggle for hybrid mode (enable/disable)
- **FR5**: Implement performance monitoring and metrics collection

#### Non-Functional Requirements
- **NFR1**: Read operations must be 10-100x faster than current AppleScript
- **NFR2**: Fallback to AppleScript must occur within 100ms of things.py failure
- **NFR3**: Memory overhead must not exceed 50MB for things.py integration
- **NFR4**: Must maintain 99.5% uptime/success rate
- **NFR5**: Zero breaking changes to existing client code

### 1.2 Success Criteria
- [ ] get_tags() returns in <200ms for 100+ tags (currently 30-60s)
- [ ] search_todos() returns in <500ms for 1000+ items
- [ ] All existing tests pass without modification
- [ ] Fallback mechanism triggers correctly on things.py failures
- [ ] Performance metrics show 10x+ improvement for read operations

### 1.3 Constraints
- Must work with existing Things 3 database location
- Cannot modify Things database directly (read-only)
- Must handle database lock scenarios gracefully
- Must support both Things 3 free and paid versions

## 2. PSEUDOCODE

### 2.1 Core Hybrid Logic
```
FUNCTION hybrid_read_operation(operation_name, parameters):
    IF hybrid_mode_enabled AND things_py_available:
        TRY:
            START performance_timer
            result = execute_things_py_operation(operation_name, parameters)
            RECORD performance_metric(operation_name, timer.elapsed, "things_py")
            RETURN convert_to_mcp_format(result)
        CATCH exception:
            LOG warning("things.py failed, falling back", exception)
            INCREMENT fallback_counter
    
    # Fallback to AppleScript
    START performance_timer
    result = execute_applescript_operation(operation_name, parameters)
    RECORD performance_metric(operation_name, timer.elapsed, "applescript")
    RETURN result

FUNCTION get_tags_hybrid(include_items):
    IF use_things_py:
        tags = things.tags()
        FOR each tag:
            IF include_items:
                tag.items = things.todos(tag=tag.name)
            ELSE:
                tag.item_count = COUNT(things.todos(tag=tag.name))
        RETURN format_tags(tags)
    ELSE:
        RETURN get_tags_applescript(include_items)
```

### 2.2 Fallback Decision Logic
```
FUNCTION should_use_things_py(operation):
    IF NOT hybrid_enabled:
        RETURN false
    IF NOT things_py_installed:
        RETURN false
    IF operation IN write_operations:
        RETURN false
    IF consecutive_failures > MAX_FAILURES:
        RETURN false
    IF database_locked:
        RETURN false
    RETURN true

FUNCTION handle_things_py_failure(operation, error):
    INCREMENT failure_count[operation]
    IF failure_count[operation] > THRESHOLD:
        DISABLE things_py_for_operation(operation)
        SCHEDULE re_enable_after(BACKOFF_PERIOD)
    LOG_ERROR(error)
    RETURN execute_applescript_fallback(operation)
```

## 3. ARCHITECTURE

### 3.1 Component Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    MCP Server Interface                  │
├─────────────────────────────────────────────────────────┤
│                    HybridToolsManager                    │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ OperationRouter │  │ FallbackMgr  │  │ PerfMon  │  │
│  └────────┬────────┘  └──────┬───────┘  └────┬─────┘  │
├───────────┴───────────────────┴───────────────┴─────────┤
│          ┌──────────────┐      ┌──────────────┐         │
│          │  things.py   │      │ AppleScript  │         │
│          │   Adapter    │      │   Manager    │         │
│          └──────┬───────┘      └──────┬───────┘         │
├─────────────────┴──────────────────────┴─────────────────┤
│          ┌──────────────┐      ┌──────────────┐         │
│          │Things SQLite │      │  Things App  │         │
│          │   Database   │      │  (via AS)    │         │
│          └──────────────┘      └──────────────┘         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow
```
Read Operation Flow:
Client Request → MCP Server → HybridToolsManager
                                    ↓
                            Operation Router
                            ↙              ↘
                    [Read Op?]            [Write Op?]
                        ↓                      ↓
                  things.py Adapter      AppleScript Mgr
                        ↓                      ↓
                  SQLite Database         Things App
                        ↓                      ↓
                  Convert Format          Parse Result
                        ↘                    ↙
                          Format Response
                                ↓
                          Client Response
```

### 3.3 Class Structure
```python
class HybridToolsManager:
    - things_adapter: ThingsPyAdapter
    - applescript_mgr: AppleScriptManager
    - fallback_mgr: FallbackManager
    - perf_monitor: PerformanceMonitor
    - config: HybridConfig
    
    + async get_todos(...) -> List[Dict]
    + async get_tags(...) -> List[Dict]
    + async add_todo(...) -> Dict
    + async update_todo(...) -> Dict

class ThingsPyAdapter:
    - db_path: str
    - cache: Dict
    
    + get_todos(...) -> List[Dict]
    + get_tags(...) -> List[Dict]
    + search(...) -> List[Dict]
    + _convert_format(things_obj) -> Dict

class FallbackManager:
    - failure_counts: Dict[str, int]
    - disabled_ops: Set[str]
    - backoff_scheduler: Scheduler
    
    + should_use_things_py(op: str) -> bool
    + record_failure(op: str, error: Exception)
    + record_success(op: str)

class PerformanceMonitor:
    - metrics: Dict[str, List[Metric]]
    - thresholds: Dict[str, float]
    
    + start_operation(op: str) -> Timer
    + end_operation(op: str, timer: Timer, method: str)
    + get_statistics() -> Dict
```

## 4. REFINEMENT

### 4.1 Edge Cases

#### Database Access Issues
- **Locked database**: Implement retry with exponential backoff
- **Missing database**: Auto-discover location or prompt user
- **Corrupted database**: Detect and fallback immediately
- **Permission denied**: Check permissions on startup, disable if needed

#### Data Consistency
- **Mid-operation changes**: Accept eventual consistency for reads
- **Timezone differences**: Normalize all dates to UTC
- **Character encoding**: Handle special characters in titles/notes
- **Large datasets**: Implement pagination for 10,000+ items

#### Performance Degradation
- **Memory leaks**: Monitor memory usage, restart adapter if needed
- **Slow queries**: Set query timeout at 5 seconds
- **Cache invalidation**: Implement smart cache with TTL
- **Connection pooling**: Reuse database connections

### 4.2 Optimization Opportunities

#### Caching Strategy
```python
class SmartCache:
    def __init__(self, ttl_seconds=30):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key, fetch_func):
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry['time'] < self.ttl:
                return entry['data']
        
        data = fetch_func()
        self.cache[key] = {'data': data, 'time': time.time()}
        return data
```

#### Batch Operations
- Combine multiple tag count queries into single SQL
- Prefetch related data when patterns detected
- Use connection pooling for parallel reads

#### Query Optimization
- Create indexes on frequently queried fields (if possible)
- Use prepared statements for repeated queries
- Implement query result streaming for large datasets

### 4.3 Testing Strategy

#### Unit Tests
```python
# test_hybrid_tools.py
class TestHybridTools:
    def test_things_py_success_path(self):
        # Mock things.py returns data
        # Verify correct format conversion
        # Verify performance metrics recorded
    
    def test_fallback_on_exception(self):
        # Mock things.py raises exception
        # Verify AppleScript fallback triggered
        # Verify failure recorded
    
    def test_fallback_disabled_after_threshold(self):
        # Trigger multiple failures
        # Verify things.py disabled for operation
        # Verify re-enable scheduled
```

#### Integration Tests
```python
# test_hybrid_integration.py
class TestHybridIntegration:
    def test_real_database_read(self):
        # Test with actual Things database
        # Verify data accuracy
        # Verify performance improvement
    
    def test_database_lock_handling(self):
        # Lock database file
        # Verify graceful fallback
        # Verify recovery after unlock
```

#### Performance Tests
```python
# benchmark_hybrid.py
def benchmark_operations():
    operations = [
        ('get_tags', {'include_items': False}),
        ('get_todos', {}),
        ('search_todos', {'query': 'test'})
    ]
    
    for op_name, params in operations:
        # Measure AppleScript time
        as_time = measure_applescript(op_name, params)
        
        # Measure things.py time
        tp_time = measure_things_py(op_name, params)
        
        improvement = as_time / tp_time
        assert improvement > 10, f"{op_name} not fast enough"
```

### 4.4 Rollout Strategy

#### Phase 1: Shadow Mode (Week 1)
- Deploy with hybrid disabled by default
- Enable for internal testing only
- Collect performance metrics
- Validate data accuracy

#### Phase 2: Beta Users (Week 2-3)
- Enable for 10% of users via feature flag
- Monitor error rates and performance
- Gather user feedback
- Fix any critical issues

#### Phase 3: Gradual Rollout (Week 4-5)
- Increase to 50% of users
- A/B test performance metrics
- Monitor system resources
- Prepare rollback plan

#### Phase 4: Full Deployment (Week 6)
- Enable for all users
- Keep AppleScript fallback active
- Monitor for 2 weeks
- Document lessons learned

## 5. CODE

### 5.1 Implementation Structure
```
src/things_mcp/
├── hybrid/
│   ├── __init__.py
│   ├── manager.py          # HybridToolsManager
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── things_py.py    # ThingsPyAdapter
│   │   └── applescript.py  # AppleScript wrapper
│   ├── fallback.py         # FallbackManager
│   ├── monitoring.py       # PerformanceMonitor
│   └── config.py          # HybridConfig
├── tests/
│   ├── unit/
│   │   ├── test_hybrid_manager.py
│   │   ├── test_things_adapter.py
│   │   └── test_fallback.py
│   └── integration/
│       ├── test_hybrid_integration.py
│       └── benchmark_hybrid.py
```

### 5.2 Key Implementation Files

#### hybrid/manager.py
```python
class HybridToolsManager:
    def __init__(self, config: HybridConfig):
        self.config = config
        self.things_adapter = ThingsPyAdapter() if config.hybrid_enabled else None
        self.applescript = AppleScriptManager()
        self.fallback = FallbackManager(config)
        self.monitor = PerformanceMonitor()
    
    async def get_tags(self, include_items: bool = False) -> List[Dict]:
        """Get tags with hybrid approach."""
        operation = 'get_tags'
        
        if self.fallback.should_use_things_py(operation):
            timer = self.monitor.start_operation(operation)
            try:
                result = await self._get_tags_things_py(include_items)
                self.monitor.end_operation(operation, timer, 'things_py')
                self.fallback.record_success(operation)
                return result
            except Exception as e:
                self.fallback.record_failure(operation, e)
                logger.warning(f"things.py failed for {operation}: {e}")
        
        # Fallback to AppleScript
        timer = self.monitor.start_operation(operation)
        result = await self._get_tags_applescript(include_items)
        self.monitor.end_operation(operation, timer, 'applescript')
        return result
```

#### hybrid/adapters/things_py.py
```python
class ThingsPyAdapter:
    def __init__(self):
        self.cache = SmartCache(ttl_seconds=30)
        self._verify_database()
    
    def get_tags(self, include_items: bool = False) -> List[Dict]:
        """Get tags using things.py."""
        cache_key = f"tags_{include_items}"
        
        def fetch():
            tags = things.tags()
            result = []
            
            for tag in tags:
                tag_dict = {
                    'id': tag.uuid,
                    'name': tag.title,
                    'uuid': tag.uuid
                }
                
                if include_items:
                    tag_dict['items'] = self._get_tag_items(tag.title)
                else:
                    # Fast count using SQL
                    tag_dict['item_count'] = self._count_tag_items(tag.title)
                
                result.append(tag_dict)
            
            return result
        
        return self.cache.get(cache_key, fetch)
```

### 5.3 Migration Checklist

- [ ] Install things.py dependency
- [ ] Create hybrid module structure
- [ ] Implement ThingsPyAdapter with format conversion
- [ ] Implement FallbackManager with circuit breaker
- [ ] Add PerformanceMonitor with metrics
- [ ] Update server.py to use HybridToolsManager
- [ ] Write comprehensive unit tests
- [ ] Write integration tests with real database
- [ ] Create performance benchmarks
- [ ] Add configuration options
- [ ] Document rollback procedure
- [ ] Create monitoring dashboard
- [ ] Plan phased rollout
- [ ] Prepare user communication

## 6. MONITORING & ALERTS

### Key Metrics to Track
- Operation latency (p50, p95, p99)
- Fallback rate per operation
- Error rate by type
- Memory usage
- Database connection count
- Cache hit rate

### Alert Thresholds
- Fallback rate > 10%: Warning
- Fallback rate > 50%: Critical
- p95 latency > 1s: Warning
- Memory > 100MB: Warning
- Error rate > 1%: Critical

## 7. ROLLBACK PLAN

If critical issues arise:
1. Set `HYBRID_ENABLED=false` in environment
2. Restart MCP server
3. All operations revert to AppleScript
4. No client code changes needed
5. Investigate and fix issues
6. Re-enable after testing
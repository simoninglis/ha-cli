# ha-automation-cli v2: WebSocket-First Architecture Plan

## Feature: Redesign for Home Assistant's WebSocket-First Architecture
**Status**: Planning  
**Started**: 2025-06-13  
**Priority**: High

## Background

After comprehensive testing of Home Assistant's WebSocket API against a live instance (HA 2025.6.0), we've confirmed the research findings: Home Assistant deliberately excludes automation CRUD operations from the WebSocket API while providing excellent real-time capabilities. Our current REST-based approach fights against HA's intended architecture.

### Key Findings from Live Testing:
- ✅ **WebSocket Features Work**: Service calls, event monitoring, trigger subscriptions
- ❌ **WebSocket CRUD Missing**: No automation create/read/update/delete operations
- ❌ **REST API Limited**: `/api/config/automation/config` returns 404 (UI-based automations)
- 🔄 **Hybrid Architecture Required**: WebSocket for real-time + file management for config

## Goals

Transform ha-automation-cli from a REST-focused tool into a WebSocket-first automation management platform that:

1. **Leverages WebSocket strengths**: Real-time monitoring, control, debugging
2. **Embraces file-based configuration**: Direct automation.yaml management
3. **Provides modern UX**: Interactive testing, live feedback, real-time monitoring
4. **Aligns with HA architecture**: Works with the platform, not against it

## Architecture Overview

```
┌─────────────────────────┐    ┌─────────────────────────┐
│     WebSocket Layer     │    │    File-Based Layer    │
├─────────────────────────┤    ├─────────────────────────┤
│ • Real-time monitoring  │    │ • automation.yaml mgmt │
│ • Service calls         │    │ • CRUD operations       │
│ • Event subscriptions   │    │ • Backup/restore        │
│ • Trigger monitoring    │    │ • Template generation   │
│ • Interactive testing   │    │ • Migration tools       │
└─────────────────────────┘    └─────────────────────────┘
               │                          │
               └──────────┬───────────────┘
                         │
            ┌─────────────────────────┐
            │   Enhanced CLI Tool     │
            ├─────────────────────────┤
            │ • Unified commands      │
            │ • Live monitoring       │
            │ • Interactive modes     │
            │ • Configuration mgmt    │
            └─────────────────────────┘
```

## Implementation Phases

### Phase 1: Enhanced WebSocket Foundation 🚀
**Duration**: 2-3 days  
**Status**: Pending

#### 1.1 Update HAClient WebSocket Capabilities
- [ ] Add real-time event subscription management
- [ ] Implement service call wrapper for automation control
- [ ] Add trigger subscription for automation testing
- [ ] Create connection management with auto-reconnection
- [ ] Add event filtering and routing
- [ ] **Tests**: Write test_websocket_client.py with mocked WebSocket connections

#### 1.2 Create Real-Time Monitoring Services
- [ ] **AutomationMonitor**: Real-time automation state tracking
- [ ] **TriggerTester**: Interactive trigger monitoring and testing
- [ ] **EventAnalyzer**: Automation event correlation and analysis
- [ ] **ServiceController**: WebSocket-based automation control
- [ ] **Tests**: Write unit tests for each service with mock WebSocket data
- [ ] **Tests**: Integration tests using recorded WebSocket sessions

#### 1.3 Update CLI Commands for WebSocket Features
- [ ] `ha-automation monitor` - Live automation state monitoring
- [ ] `ha-automation test-trigger` - Interactive trigger testing
- [ ] `ha-automation control` - Enable/disable automations via WebSocket
- [ ] `ha-automation events` - Stream automation-related events

### Phase 2: File-Based Configuration Management 📁
**Duration**: 3-4 days  
**Status**: Pending

#### 2.1 Direct File Management
- [ ] **FileAutomationCRUD**: Direct automation.yaml manipulation
- [ ] **ConfigurationManager**: Backup, restore, versioning
- [ ] **TemplateEngine**: Generate automation templates
- [ ] **ValidationEngine**: Local automation validation (without WebSocket)

#### 2.2 Home Assistant Integration
- [ ] **ReloadTrigger**: Trigger HA configuration reload after changes
- [ ] **FileWatcher**: Monitor automation.yaml for external changes
- [ ] **ConflictResolver**: Handle concurrent file modifications
- [ ] **MigrationTools**: Convert between UI and file-based automations

#### 2.3 Updated CRUD Commands
- [ ] `ha-automation create` - Create automation in file + reload
- [ ] `ha-automation update` - Update automation in file + reload
- [ ] `ha-automation delete` - Remove from file + reload
- [ ] `ha-automation backup` - Backup automation configurations
- [ ] `ha-automation restore` - Restore from backup

### Phase 3: Interactive Features 🎮
**Duration**: 2-3 days  
**Status**: Pending

#### 3.1 Live Testing Mode
- [ ] **InteractiveTester**: Real-time automation development environment
- [ ] **TriggerSimulator**: Simulate triggers and monitor responses
- [ ] **DebugConsole**: Live automation debugging with event correlation
- [ ] **PerformanceMonitor**: Track automation execution metrics

#### 3.2 Enhanced User Experience
- [ ] **RichConsole**: Colored output, progress bars, live updates
- [ ] **ConfigurationWizard**: Interactive automation creation
- [ ] **ConflictResolution**: Interactive file conflict resolution
- [ ] **AutoCompletion**: Entity ID and service autocompletion

#### 3.3 Advanced Commands
- [ ] `ha-automation develop` - Interactive development mode
- [ ] `ha-automation debug <automation_id>` - Live debugging session
- [ ] `ha-automation wizard` - Guided automation creation
- [ ] `ha-automation analyze` - Performance and usage analysis

### Phase 4: Advanced Integration 🔗
**Duration**: 2-3 days  
**Status**: Pending

#### 4.1 External Tool Integration
- [ ] **VSCodeIntegration**: Extension for automation editing
- [ ] **NodeRedBridge**: Convert between Node-RED flows and HA automations
- [ ] **GitIntegration**: Version control for automation configurations
- [ ] **CIIntegration**: Automation testing in CI/CD pipelines

#### 4.2 Ecosystem Features
- [ ] **AutomationLibrary**: Shareable automation templates
- [ ] **CommunityHub**: Import/export popular automation patterns
- [ ] **DocumentationGenerator**: Auto-generate automation documentation
- [ ] **TestSuiteGenerator**: Create test suites for automations

#### 4.3 Enterprise Features
- [ ] **MultiInstance**: Manage automations across multiple HA instances
- [ ] **RoleBasedAccess**: User permissions for automation management
- [ ] **AuditLogging**: Track automation changes and executions
- [ ] **ComplianceReporting**: Generate automation compliance reports

## Technical Architecture

### Core Components

#### 1. Enhanced HAClient
```python
class HAClient:
    async def subscribe_events(self, event_type: str, filter_func: Callable = None)
    async def subscribe_automation_states(self) -> AsyncIterator[AutomationStateEvent]
    async def subscribe_trigger(self, trigger_config: dict) -> AsyncIterator[TriggerEvent]
    async def call_automation_service(self, service: str, entity_ids: list)
    async def monitor_automation_performance(self) -> AsyncIterator[PerformanceMetric]
```

#### 2. File Management Layer
```python
class FileAutomationManager:
    def load_automations(self) -> list[Automation]
    def save_automation(self, automation: Automation) -> None
    def delete_automation(self, automation_id: str) -> None
    def backup_configuration(self) -> BackupResult
    def restore_configuration(self, backup_path: Path) -> None
    def trigger_ha_reload(self) -> ReloadResult
```

#### 3. Real-Time Services
```python
class AutomationMonitor:
    async def start_monitoring(self) -> None
    async def get_live_states(self) -> dict[str, AutomationState]
    async def track_executions(self) -> AsyncIterator[ExecutionEvent]

class InteractiveTester:
    async def test_trigger(self, trigger_config: dict) -> TestResult
    async def simulate_conditions(self, conditions: list) -> SimulationResult
    async def dry_run_actions(self, actions: list) -> ActionPreview
```

### CLI Command Structure

```
ha-automation
├── monitor                 # Real-time monitoring (WebSocket)
├── control                 # Enable/disable via WebSocket
├── events                  # Stream automation events
├── test-trigger           # Interactive trigger testing
├── create <file>          # Create automation (File + Reload)
├── update <id> <file>     # Update automation (File + Reload)
├── delete <id>            # Delete automation (File + Reload)
├── list                   # List automations (File or WebSocket)
├── backup                 # Backup automation config
├── restore <backup>       # Restore from backup
├── develop                # Interactive development mode
├── debug <id>             # Live debugging session
├── wizard                 # Guided creation
├── analyze                # Performance analysis
└── version                # Tool version
```

## Migration Strategy

### Phase 1: Backwards Compatibility
- Keep existing commands working with new backend
- Add deprecation warnings for REST-only features
- Provide migration path for existing users

### Phase 2: Enhanced Features
- Introduce new WebSocket-based commands alongside existing ones
- Allow users to opt-in to new functionality
- Provide clear documentation on feature differences

### Phase 3: Full Transition
- Make WebSocket-first the default behavior
- Retire REST-only fallbacks (with grace period)
- Complete migration to new architecture

## Testing Strategy

### Unit Tests

#### Update Existing Tests
- [ ] **test_models.py**: Add tests for triggers/conditions/actions format support
  - Test model validator converting `triggers` → `trigger`
  - Test handling of both singular and plural formats
  - Test serialization preserving correct format
- [ ] **test_cli.py**: Update for new WebSocket-based commands
  - Remove tests for REST automation CRUD (404 responses)
  - Add tests for new monitor/control/events commands
  - Test dry-run with file-based operations

#### New Unit Tests
- [ ] **test_websocket_client.py**: WebSocket connection management
  - Connection establishment and authentication
  - Auto-reconnection with exponential backoff
  - Message size handling (10MB+ responses)
  - Connection pooling for multiple subscriptions
- [ ] **test_file_manager.py**: File-based automation management
  - YAML file reading/writing with preservation
  - Backup and restore operations
  - Conflict detection and resolution
  - Atomic file operations
- [ ] **test_event_processor.py**: Event filtering and routing
  - Automation state change detection
  - Event correlation and deduplication
  - Performance with high event volumes

### Integration Tests

#### Update Existing Tests
- [ ] **test_integration_client.py**: Replace REST with WebSocket tests
  - Remove automation CRUD REST tests (404 endpoints)
  - Add WebSocket service call tests
  - Add event subscription tests
  - Add trigger subscription tests
- [ ] **test_integration_service.py**: Update for file-based operations
  - Test file-based CRUD with HA reload
  - Test backup/restore workflows
  - Test conflict resolution scenarios

#### New Integration Tests
- [ ] **test_integration_websocket.py**: Live WebSocket testing
  ```python
  async def test_automation_control_via_websocket()
  async def test_event_subscription_filtering()
  async def test_trigger_subscription_monitoring()
  async def test_concurrent_subscriptions()
  async def test_reconnection_during_ha_restart()
  ```
- [ ] **test_integration_file_ha.py**: File + HA integration
  ```python
  async def test_create_automation_and_reload()
  async def test_update_automation_with_backup()
  async def test_delete_automation_with_confirmation()
  async def test_bulk_operations_with_rollback()
  ```
- [ ] **test_integration_monitoring.py**: Real-time monitoring
  ```python
  async def test_live_automation_state_tracking()
  async def test_execution_performance_metrics()
  async def test_trigger_correlation_analysis()
  ```

### End-to-End Tests
- [ ] **test_e2e_automation_lifecycle.py**: Complete workflows
  - Create automation via wizard → test trigger → monitor execution
  - Import Node-RED flow → convert → deploy → verify
  - Debug failing automation → fix → test → deploy
- [ ] **test_e2e_migration.py**: Migration scenarios
  - REST to WebSocket command migration
  - UI automation to file-based conversion
  - Backup before major changes workflow

### Performance Tests
- [ ] **test_performance_websocket.py**: WebSocket scalability
  - Handle 1000+ automation state changes/second
  - Monitor 100+ automations simultaneously
  - Memory usage under 50MB for typical scenarios
- [ ] **test_performance_file.py**: File operation efficiency
  - Load/save 500+ automations in < 1 second
  - Concurrent file access handling
  - Large automation file parsing

### User Acceptance Tests
- [ ] **Interactive mode testing**: Real user workflows
  - First-time user creating automation
  - Power user debugging complex automation
  - Migration from UI to file-based management
- [ ] **Cross-platform testing**: OS compatibility
  - Windows path handling
  - macOS file permissions
  - Linux file watching
- [ ] **HA version testing**: Compatibility matrix
  - HA 2023.x through 2025.x
  - Core vs Supervised vs OS installations
  - Different authentication methods

## Risk Assessment

### High Risk
- **WebSocket connection stability**: Implement robust reconnection logic
- **File system race conditions**: Add proper locking and conflict resolution
- **HA version compatibility**: Test across multiple HA versions

### Medium Risk
- **Performance with large automation sets**: Implement streaming and pagination
- **User experience complexity**: Provide clear documentation and examples
- **Breaking changes**: Maintain backwards compatibility during transition

### Low Risk
- **WebSocket API changes**: HA's WebSocket API is stable and well-documented
- **File format changes**: YAML automation format is standardized
- **Community adoption**: Clear benefits and migration path

## Success Metrics

### Technical Metrics
- [ ] WebSocket connection uptime > 99.9%
- [ ] Automation operation latency < 100ms
- [ ] File operation success rate > 99.5%
- [ ] Memory usage < 50MB for typical use cases

### User Experience Metrics
- [ ] Command execution time < 2 seconds
- [ ] Interactive mode responsiveness < 100ms
- [ ] Documentation completeness > 95%
- [ ] User satisfaction score > 4.5/5

### Functional Metrics
- [ ] All existing features work with new architecture
- [ ] Real-time monitoring accuracy > 99%
- [ ] Automation validation accuracy > 98%
- [ ] Cross-platform compatibility 100%

## Dependencies

### External Dependencies
- **Home Assistant 2023.x+**: WebSocket API features
- **Python 3.11+**: Modern async/await patterns
- **Rich library**: Enhanced terminal output
- **Watchdog**: File system monitoring

### Internal Dependencies
- **Existing codebase**: Gradual migration approach
- **Test suite**: Comprehensive coverage maintenance
- **Documentation**: Updated for new architecture
- **CI/CD pipeline**: Automated testing and deployment

## Timeline

### Week 1: Foundation (Phase 1)
- Days 1-2: Enhanced WebSocket client implementation
- Days 3-4: Real-time monitoring services
- Days 5-7: Updated CLI commands and testing

### Week 2: Configuration Management (Phase 2)
- Days 1-3: File-based automation management
- Days 4-5: HA integration and reload triggers
- Days 6-7: Updated CRUD commands and testing

### Week 3: Interactive Features (Phase 3)
- Days 1-2: Live testing and debugging modes
- Days 3-4: Enhanced user experience features
- Days 5-7: Advanced commands and testing

### Week 4: Polish and Integration (Phase 4)
- Days 1-3: External tool integration
- Days 4-5: Documentation and examples
- Days 6-7: Final testing and release preparation

## Acceptance Criteria

### Must Have
- [ ] All WebSocket features from testing work reliably
- [ ] File-based automation CRUD operations
- [ ] Real-time automation monitoring
- [ ] Backwards compatibility with existing commands
- [ ] Comprehensive error handling and recovery

### Should Have
- [ ] Interactive development mode
- [ ] Live debugging capabilities
- [ ] Performance monitoring and analysis
- [ ] Rich terminal output and user experience
- [ ] Backup and restore functionality

### Could Have
- [ ] External tool integrations (VS Code, Node-RED)
- [ ] Community automation library
- [ ] Multi-instance management
- [ ] Advanced analytics and reporting

## Notes

This plan represents a fundamental architectural shift from fighting Home Assistant's design to embracing it. By leveraging WebSocket strengths for real-time operations and file-based approaches for configuration management, we create a tool that's both more powerful and more aligned with the platform's philosophy.

The phased approach ensures we can maintain backwards compatibility while gradually introducing the enhanced capabilities, providing a smooth migration path for existing users while opening up new possibilities for automation management.
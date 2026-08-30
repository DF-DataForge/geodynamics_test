# Geodynamics

## Overview
This module provides comprehensive integration between Odoo and Geodynamics (Intellitracer API) by Data Forge, enabling seamless synchronization of planning data, employee management, project coordination, and field service operations. It bridges Odoo's project management, HR, and field service capabilities with Geodynamics' advanced tracking and planning system.

## Dependencies
- `base` - Core Odoo functionality
- `hr` - Human Resources management
- `project` - Project management
- `industry_fsm` - Field Service Management
- `account` - Accounting integration

## Key Features

### 1. API Integration and Configuration

#### Geodynamics Connection Management
- **Secure API Authentication**: HTTPBasicAuth integration with Intellitracer API v2
- **Multi-Company Support**: Company-specific API credentials and configurations
- **Connection Testing**: Built-in connection validation with status feedback
- **Configuration Panel**: Dedicated settings section under General Settings → Geodynamics
- **Environment Flexibility**: Configurable base URL and authentication parameters

#### Settings Configuration
- **API Credentials Management**: Secure storage of login, password, and company identifiers
- **Connection Parameters**: Configurable API endpoints and authentication methods
- **System Integration**: Seamless integration with Odoo's configuration system
- **Validation Tools**: Real-time connection testing and status reporting

### 2. Enhanced Employee and User Management

#### Employee Extensions (`hr.employee`)
- **Geodynamics ID Integration**: Links employees to Geodynamics system identifiers
- **Synchronization Status**: Track which employees are synchronized with Geodynamics
- **Planning Integration**: Employee availability and scheduling coordination
- **Field Service Assignment**: Enhanced employee assignment for field service tasks

#### User Management (`res.users`)
- **Geodynamics User Mapping**: Connect Odoo users to Geodynamics user accounts
- **Permission Synchronization**: Coordinate access rights between systems
- **Activity Tracking**: Monitor user activities across both platforms
- **Authentication Bridge**: Seamless user experience across integrated systems

### 3. Advanced Project and Task Management

#### Project Extensions (`project.project`)
- **Geodynamics Project Mapping**: Bidirectional project synchronization
- **Planning Coordination**: Integrated project planning across both systems
- **Resource Allocation**: Enhanced resource management with Geodynamics data
- **Status Synchronization**: Real-time project status updates

#### Task Management (`project.task`)
- **Enhanced Assignment Logic**: Dual-mode assignment (employee/user mode)
- **Geodynamics Planning Integration**: `df_gd_planning_ids` for planning data
- **POI (Point of Interest) Tracking**: `df_geodynamics_poi_id` for location-based tasks
- **Assignment Validation**: Automatic detection of employees with/without Geodynamics IDs
- **Overlap Detection**: `df_gd_planning_overlapped_ids` for scheduling conflict identification
- **Planning Modes**: Support for both employee-based and user-based workflows

### 4. Partner and Customer Management

#### Partner Extensions (`res.partner`)
- **Geodynamics Customer Mapping**: Link customers to Geodynamics system
- **Location Synchronization**: Coordinate customer locations and addresses
- **Service History**: Integrated service history across both platforms
- **Contact Information Sync**: Maintain consistent contact data

### 5. Planning and Scheduling System

#### Geodynamics Planning (`df.geodynamics.planning`)
- **Comprehensive Planning Records**: Dedicated model for Geodynamics planning data
- **Task Association**: Direct linking to project tasks
- **Schedule Overlap Detection**: Automatic identification of scheduling conflicts
- **Resource Optimization**: Enhanced resource allocation and planning
- **Real-time Synchronization**: Bidirectional planning data exchange

#### POI Type Management (`df.geodynamics.poi.type`)
- **Location Classification**: Manage different types of points of interest
- **Service Categorization**: Classify service locations and requirements
- **Integration Mapping**: Connect Odoo locations to Geodynamics POI system

### 6. Accounting Integration

#### Account Analytics (`account.analytic`)
- **Cost Center Integration**: Link analytical accounts to Geodynamics projects
- **Time Tracking**: Coordinate time tracking across both systems
- **Cost Allocation**: Enhanced cost allocation with Geodynamics data
- **Financial Reporting**: Integrated financial reporting capabilities

## Technical Implementation

### API Handler (`GeodynamicsHandler`)
```python
class GeodynamicsHandler:
    def __init__(self, gd_login, gd_password, gd_company, environ):
        self.baseUrl = 'https://api.intellitracer.be/api/v2'
        self.auth = HTTPBasicAuth(str(gd_login) + '|' + str(gd_company), str(gd_password))
```

#### Core Features:
- **Secure Authentication**: Company-specific authentication with proper credential handling
- **Error Handling**: Comprehensive error handling and logging
- **Connection Testing**: Built-in connection validation methods
- **Request Management**: Efficient API request handling and response processing

### Data Models Architecture
- **Inheritance Pattern**: Extends existing Odoo models without disrupting core functionality
- **Computed Fields**: Dynamic fields that automatically calculate Geodynamics integration status
- **Relational Integrity**: Maintains proper relationships between Odoo and Geodynamics entities
- **Synchronization Logic**: Automated synchronization processes with conflict resolution

## User Interface Enhancements

### Planning Views
- **Dedicated Planning Interface**: Specialized views for Geodynamics planning data
- **Resource Allocation Views**: Visual resource management with Geodynamics integration
- **Conflict Resolution**: Visual indicators for scheduling conflicts and overlaps
- **Assignment Tracking**: Clear visibility of employee/user assignments

### Configuration Interface
- **Settings Panel**: User-friendly configuration interface in General Settings
- **Connection Testing**: Real-time connection status with visual feedback
- **Credential Management**: Secure credential storage and validation
- **System Status**: Comprehensive system integration status dashboard

### Enhanced Form Views
- **Task Forms**: Enhanced task forms with Geodynamics-specific fields
- **Employee Forms**: Extended employee forms with integration status
- **Project Forms**: Enhanced project forms with planning coordination
- **Partner Forms**: Extended partner forms with Geodynamics mapping

## Business Benefits

### Improved Planning Efficiency
- **Unified Planning**: Single interface for both Odoo and Geodynamics planning
- **Conflict Prevention**: Automatic detection and prevention of scheduling conflicts
- **Resource Optimization**: Better resource allocation with integrated data
- **Real-time Updates**: Immediate synchronization of planning changes

### Enhanced Field Service Operations
- **Location Tracking**: Advanced POI tracking and management
- **Employee Coordination**: Better coordination of field service teams
- **Customer Integration**: Seamless customer data across both systems
- **Service History**: Comprehensive service history and tracking

### Streamlined Administration
- **Single Point of Control**: Manage integration from within Odoo
- **Automated Synchronization**: Reduce manual data entry and errors
- **Comprehensive Reporting**: Unified reporting across both systems
- **Scalable Integration**: Support for multi-company and complex organizational structures

## Configuration and Setup

### Initial Setup
1. **Module Installation**: Install the Geodynamics module from Apps
2. **API Configuration**: Navigate to Settings → General Settings → Geodynamics
3. **Credential Entry**: Enter Geodynamics API credentials (login, password, company)
4. **Connection Testing**: Use the built-in test function to verify connectivity
5. **Data Mapping**: Configure employee and user mappings to Geodynamics

### Employee Configuration
1. **Geodynamics ID Assignment**: Assign Geodynamics IDs to relevant employees
2. **User Mapping**: Map Odoo users to Geodynamics user accounts
3. **Permission Setup**: Configure appropriate access rights and permissions
4. **Synchronization Testing**: Verify employee data synchronization

### Project and Task Setup
1. **Project Mapping**: Configure project connections to Geodynamics
2. **Task Templates**: Set up task templates with Geodynamics integration
3. **Planning Configuration**: Configure planning parameters and schedules
4. **POI Setup**: Define points of interest and location types

## Usage Instructions

### Daily Operations
1. **Planning Management**: Use integrated planning views to manage schedules
2. **Task Assignment**: Assign employees to tasks with automatic Geodynamics sync
3. **Conflict Resolution**: Monitor and resolve scheduling conflicts as they arise
4. **Status Updates**: Keep both systems synchronized with real-time updates

### Reporting and Analytics
1. **Integrated Reports**: Access reports that combine Odoo and Geodynamics data
2. **Performance Metrics**: Monitor performance across both systems
3. **Resource Utilization**: Analyze resource utilization and efficiency
4. **Cost Analysis**: Comprehensive cost analysis with integrated data

## Troubleshooting

### Common Issues
1. **Connection Problems**: Verify API credentials and network connectivity
2. **Synchronization Errors**: Check data mapping and field compatibility
3. **Planning Conflicts**: Use conflict resolution tools to address overlaps
4. **Performance Issues**: Monitor API call frequency and optimize as needed

### Debug Information
- **Connection Status**: Monitor connection status in settings panel
- **API Logs**: Review API call logs for troubleshooting
- **Data Validation**: Verify data integrity between systems
- **Error Handling**: Comprehensive error logging and reporting

## Version Information
- **Version**: 18.0.0.0.1
- **Author**: Data Forge
- **Website**: https://www.data-forge.be
- **License**: OPL-1 (Odoo Proprietary License v1.0)
- **Compatibility**: Odoo 18.0+

## Installation
1. Ensure all dependencies are installed: `base`, `hr`, `project`, `industry_fsm`, `account`
2. Place the module in your addons path
3. Update Apps list and install "Geodynamics"
4. Configure API credentials in Settings → General Settings → Geodynamics
5. Test connection and configure data mappings
6. Set up employee and project synchronization

## API Integration Details
- **Base URL**: https://api.intellitracer.be/api/v2
- **Authentication**: HTTPBasicAuth with company-specific formatting
- **Data Exchange**: Bidirectional synchronization with conflict resolution
- **Rate Limiting**: Appropriate API call management and throttling
- **Error Recovery**: Robust error handling and retry mechanisms

---

*This module provides seamless integration between Odoo and Geodynamics, enabling businesses to leverage the power of both systems while maintaining data consistency and operational efficiency across planning, project management, and field service operations.*

---

## License

Copyright 2025-2026 Data Forge (https://www.data-forge.be)

This module is licensed under the **Odoo Proprietary License v1.0 (OPL-1)**.
It may only be used if you have purchased a valid license from Data Forge or
have received a written agreement from Data Forge.

Publishing, distributing, sublicensing or selling copies of this module —
modified or unmodified — is forbidden.

See the [LICENSE](LICENSE) and [COPYRIGHT](COPYRIGHT) files for full details.

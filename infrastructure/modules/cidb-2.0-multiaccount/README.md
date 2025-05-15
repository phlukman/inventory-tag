# CIDB 2.0 Multi-Account Architecture

## ⚠️ IMPORTANT: Performance Improvements Needed

This multi-account implementation **does not yet include the performance improvements** that have been implemented in the pre-multiaccount version. The following critical improvements need to be synced to this version:

1. **Lambda Configuration Updates**:
   - Increase Lambda timeouts from 20/300 seconds to 900 seconds (15 minutes)
   - Increase memory allocation from 512MB to 1024MB

2. **SQS Batch Processing**:
   - Increase batch size from 1 to 25 messages
   - Add a 30-second batching window

3. **Code Enhancements**:
   - Update message batch processing to handle multiple messages efficiently
   - Improve error handling for individual message failures
   - Implement detailed, contextual logging

4. **S3 Locking Configuration**:
   - Add environment variables for locking parameters (LOCK_TIMEOUT_SECONDS, etc.)
   - Implement improved locking with retry logic

These improvements are essential for handling large volumes of data (1500+ IAM policies) and should be applied to this multiaccount version to maintain consistent performance characteristics with the pre-multiaccount implementation.

## Overview

The CIDB 2.0 Multi-Account architecture is an enhanced version of the original inventory tagging system. It's designed to efficiently collect, process, and report on AWS resources across multiple accounts and services at scale. This implementation focuses on maintaining the original application code structure while introducing service-specific processing, improved error handling, and enhanced scalability.

```mermaid
flowchart TD
    A["Step Functions Workflow"] --> B["Parallel Service Collection"]
    
    B --> C1["IAM Collector"]
    B --> C2["KMS Collector"]
    B --> C3["EC2 Collector"]
    B --> C4["S3 Collector"]
    
    C1 --> D1["IAM Reporter"]
    C2 --> D2["KMS Reporter"]
    C3 --> D3["EC2 Reporter"]
    C4 --> D4["S3 Reporter"]
    
    D1 --> E["Consolidator"]
    D2 --> E
    D3 --> E
    D4 --> E
    
    classDef workflow fill:#f9f,stroke:#333,stroke-width:4px,color:#000
    classDef parallel fill:#bbf,stroke:#333,stroke-width:4px,color:#000
    classDef collector fill:#444,stroke:#fff,stroke-width:2px,color:#fff
    classDef reporter fill:#555,stroke:#fff,stroke-width:2px,color:#fff
    classDef consolidator fill:#bfb,stroke:#333,stroke-width:4px,color:#000
    
    class A workflow
    class B parallel
    class C1,C2,C3,C4 collector
    class D1,D2,D3,D4 reporter
    class E consolidator
```

## Key Improvements

### 1. Service-Specific Architecture

The new architecture separates resource collection by service type (IAM, KMS, EC2, S3), allowing for:

- **Independent Scaling**: Each service can be scaled based on its specific needs
- **Reduced Lambda Timeouts**: By focusing on one service at a time, we reduce the risk of timeouts
- **Parallel Processing**: Services can be processed concurrently, reducing overall execution time
- **Better Error Isolation**: Issues with one service won't affect others

### 2. Multi-Account Support

Enhanced to efficiently handle large-scale resource collection across multiple AWS accounts:

- **Concurrent Account Processing**: Configurable concurrency limits for account processing
- **Cross-Account Role Assumption**: Streamlined process for assuming roles across accounts
- **Account-Level Error Handling**: Better isolation of account-specific issues
- **Configurable Account Lists**: Support for environment variable or event-based account lists

```mermaid
flowchart LR
    A["Collector Lambda"] --> B{"Parallel Processing"}
    B --> C1["Account 1"]
    B --> C2["Account 2"]
    B --> C3["Account n"]
    
    C1 --> D1["Assume Role"]
    C2 --> D2["Assume Role"]
    C3 --> D3["Assume Role"]
    
    D1 --> E1["Collect Resources"]
    D2 --> E2["Collect Resources"]
    D3 --> E3["Collect Resources"]
    
    E1 --> F["SNS Topic"]
    E2 --> F
    E3 --> F
    
    classDef lambda fill:#f96,stroke:#333,stroke-width:4px,color:#000
    classDef parallel fill:#bbf,stroke:#333,stroke-width:2px,color:#000,shape:diamond
    classDef account fill:#444,stroke:#fff,stroke-width:2px,color:#fff
    classDef role fill:#557,stroke:#fff,stroke-width:2px,color:#fff
    classDef collect fill:#355,stroke:#fff,stroke-width:2px,color:#fff
    classDef sns fill:#9cf,stroke:#333,stroke-width:4px,color:#000
    
    class A lambda
    class B parallel
    class C1,C2,C3 account
    class D1,D2,D3 role
    class E1,E2,E3 collect
    class F sns
```

### 3. Step Functions Orchestration

A new Step Functions workflow orchestrates the entire process:

- **Parallel Execution**: Collects from different services simultaneously
- **Coordinated Waiting**: Ensures all processing is complete before consolidation
- **Error Handling**: Built-in retry logic and error state transitions
- **Visualization**: Provides visibility into the execution flow and status

```mermaid
stateDiagram-v2
    [*] --> ParallelServiceCollection
    ParallelServiceCollection --> WaitForMessageProcessing: "All service collections complete"
    WaitForMessageProcessing --> RunConsolidator: "Wait 5 minutes"
    
    RunConsolidator --> WorkflowComplete: Success
    RunConsolidator --> WorkflowCompleteWithErrors: Failure
    
    state ParallelServiceCollection {
        state "Service Collections" as parallel <<fork>>
        parallel: Runs all service collectors in parallel
        
        [*] --> parallel
        
        parallel --> IAMCollection
        parallel --> KMSCollection
        parallel --> EC2Collection
        parallel --> S3Collection
        
        state IAMCollection {
            description: "IAM Resource Collection"
        }
        
        state KMSCollection {
            description: "KMS Resource Collection"
        }
        
        state EC2Collection {
            description: "EC2 Resource Collection"
        }
        
        state S3Collection {
            description: "S3 Resource Collection"
        }
        
        IAMCollection --> IAMSuccess: Success
        IAMCollection --> IAMFailure: "Failure (retry 2x)"
        
        KMSCollection --> KMSSuccess: Success
        KMSCollection --> KMSFailure: "Failure (retry 2x)"
        
        EC2Collection --> EC2Success: Success
        EC2Collection --> EC2Failure: "Failure (retry 2x)"
        
        S3Collection --> S3Success: Success
        S3Collection --> S3Failure: "Failure (retry 2x)"
    }
    
    note right of WaitForMessageProcessing: "Allows time for SQS/SNS message processing"
    note right of RunConsolidator: "Merges all service reports"
    
    state WorkflowComplete {
        description: "All resources collected and consolidated successfully"
    }
    
    state WorkflowCompleteWithErrors {
        description: "Some services failed but workflow completed"
    }
    
    WorkflowComplete --> [*]
    WorkflowCompleteWithErrors --> [*]
```

### 4. Improved Error Handling

Enhanced error handling mechanisms throughout the system:

- **Circuit Breaker Pattern**: Prevents cascading failures when services are unavailable
- **Structured Error Reporting**: Consistent error format across all components
- **Retries with Backoff**: Intelligent retry logic for transient failures
- **CloudWatch Alarms**: Monitoring for critical error conditions

### 5. Consolidated Reporting

The new Consolidator Lambda function:

- **Merges Service Reports**: Combines service-specific CSV files into a single report
- **Optimized Storage**: Organizes S3 storage by service, account, and date
- **Report Format Consistency**: Ensures consistent formatting across all services
- **Historical Data Access**: Maintains historical reports in an organized hierarchy

```mermaid
flowchart TD
    A["S3 Bucket\ninventory-tagging"] --> B["cidb-2.0/"]
    
    B --> C1["temp/"]
    B --> C2["final/"]
    
    C1 --> D1["IAM/"]
    C1 --> D2["KMS/"]
    C1 --> D3["EC2/"]
    C1 --> D4["S3/"]
    
    D1 --> E1["account-123456789012/"]
    D1 --> E2["account-234567890123/"]
    
    E1 --> F1["2025-05-15_iam_report.csv"]
    
    C2 --> G1["daily/"]
    C2 --> G2["weekly/"]
    C2 --> G3["monthly/"]
    
    G1 --> H1["2025-05-15_consolidated_report.csv"]
    
    classDef bucket fill:#ffd,stroke:#333,stroke-width:4px,color:#000
    classDef root fill:#ddd,stroke:#333,stroke-width:2px,color:#000
    classDef mainDir fill:#ddf,stroke:#333,stroke-width:2px,color:#000
    classDef serviceDir fill:#466,stroke:#fff,stroke-width:1px,color:#fff
    classDef accountDir fill:#488,stroke:#fff,stroke-width:1px,color:#fff
    classDef reportFile fill:#ada,stroke:#333,stroke-width:1px,color:#000
    classDef finalDir fill:#dfd,stroke:#333,stroke-width:2px,color:#000
    classDef finalFile fill:#ddf,stroke:#333,stroke-width:2px,color:#000
    
    class A bucket
    class B root
    class C1 mainDir
    class C2 finalDir
    class D1,D2,D3,D4 serviceDir
    class E1,E2 accountDir
    class F1 reportFile
    class G1,G2,G3 mainDir
    class H1 finalFile
    
    %% Add notes for clarity
    subgraph "Temporary Service-Specific Reports"
        C1
        D1
        D2
        D3
        D4
        E1
        E2
        F1
    end
    
    subgraph "Final Consolidated Reports"
        C2
        G1
        G2
        G3
        H1
    end
```

### 6. S3 Storage Organization

The S3 storage is organized in a hierarchical structure to facilitate efficient access and management of reports.

## Component Overview

### Collector Lambda

- **Purpose**: Collects resources from AWS accounts based on service type
- **Concurrency**: Processes multiple accounts in parallel
- **Configuration**: Service-specific via environment variables
- **Output**: Publishes resources to service-specific SNS topics

### Reporter Lambda

- **Purpose**: Processes service-specific messages from SQS
- **Functionality**: Creates CSV reports for each service and account
- **Storage**: Organizes reports in S3 with a structured prefix hierarchy
- **Integration**: Indicates completion for the consolidation step

### Consolidator Lambda

- **Purpose**: Merges service-specific reports into a final consolidated report
- **Processing**: Combines data from multiple service reports
- **Output**: Produces a unified CSV with consistent formatting
- **Cleanup**: Optionally removes temporary service-specific reports

### Step Functions Workflow

- **Orchestration**: Manages the entire workflow from collection to consolidation
- **Parallelism**: Runs service collections concurrently
- **Error Handling**: Provides retry capabilities and failure tracking
- **Status Tracking**: Maintains state information throughout the process

## Environment Variables

### Collector Lambda

- `SERVICE_TYPE`: Type of service to collect (IAM, KMS, EC2, S3)
- `SNS_TOPIC_ARN`: ARN of the service-specific SNS topic
- `ACCOUNTS`: Comma-separated list or JSON array of account IDs
- `ASSUME_ROLE`: Role name to assume in target accounts
- `MAX_ACCOUNTS_CONCURRENCY`: Number of accounts to process concurrently
- `MAX_WORKERS`: Maximum number of worker threads for resource processing

### Reporter Lambda

- `SERVICE_TYPE`: Type of service being reported
- `BUCKET_NAME`: S3 bucket for storing reports
- `TEMP_PREFIX`: Prefix for temporary report storage
- `FINAL_PREFIX`: Prefix for final report storage

### Consolidator Lambda

- `BUCKET_NAME`: S3 bucket containing service reports
- `PREFIX`: Base prefix for all reports
- `SERVICES`: JSON array of services to consolidate

## Service-Specific Implementation

### IAM Resources

The implementation for IAM includes:
- Policy collection across multiple accounts
- Tag management for IAM policies
- Detailed policy properties reporting

### KMS Resources

The implementation for KMS includes:
- Key collection across multiple accounts
- Tag management for KMS keys
- Key usage and rotation status tracking

### EC2 Resources

The implementation for EC2 includes:
- Instance inventory across multiple accounts
- Tag management for EC2 instances
- Instance type and state reporting

### S3 Resources

The implementation for S3 includes:
- Bucket inventory across multiple accounts
- Tag management for S3 buckets
- Bucket policy and encryption status reporting

## Getting Started

### Prerequisites

- AWS account with appropriate permissions
- Terraform for infrastructure deployment
- Python 3.9 or later

### Deployment

To deploy the CIDB 2.0 Multi-Account architecture:

1. Update the required variables in the `terraform.tfvars` file
2. Run Terraform commands to deploy:
   ```
   terraform init
   terraform plan
   terraform apply
   ```

### Execution

The Step Functions workflow can be triggered:
- On a schedule using EventBridge rules
- Manually through the AWS Management Console
- Via the AWS CLI or SDKs

## Security Considerations

- **IAM Roles**: Uses least privilege IAM roles for all components
- **Cross-Account Access**: Securely assumes roles across accounts
- **Data Protection**: Ensures sensitive data is properly handled
- **Monitoring**: CloudWatch alarms for security-related events

## Performance Optimization

- **Concurrency Control**: Configurable parameters for parallel processing
- **Circuit Breakers**: Prevents resource exhaustion during failures
- **Batch Processing**: Efficient handling of large data volumes
- **S3 Organization**: Optimized storage structure for quick access

## Monitoring and Troubleshooting

- **CloudWatch Logs**: Detailed logging for all Lambda functions
- **CloudWatch Metrics**: Performance and error metrics
- **CloudWatch Alarms**: Notifications for critical conditions
- **X-Ray Tracing**: Optional distributed tracing for debugging

## Future Enhancements

- **Additional Services**: Support for more AWS services
- **Custom Resource Handlers**: Extensible framework for custom resource types
- **Advanced Reporting**: Enhanced reporting capabilities and visualizations
- **Cost Optimization**: Refined resource utilization and cost reduction strategies

## Contributing

When contributing to this project, please follow the existing code structure and patterns. The core design principle is to maintain the original application code while enhancing the infrastructure for multi-account operations.

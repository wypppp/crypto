> ## Documentation Index
>
> Fetch the complete documentation index at: https://docs.dune.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Pricing & Best Practices

> Credit consumption, optimization tips, and best practices for dbt on Dune

Data Transformations is an **Enterprise-only feature** with usage-based credit consumption.

<Note>
  **CI/CD and Credit Usage**

  Each dbt execution consumes credits, whether triggered locally, through CI/CD, or on a schedule. The template repository ships with automated CI/CD triggers **disabled by default** so you can enable them when you're ready. See [CI/CD & Workflows](/api-reference/connectors/dbt/cicd-workflows) for tips on managing costs in automated pipelines.

## Pricing & Credits

### Credit Consumption

Your credit usage includes three components:

#### Compute Credits

* Same as Fluid Engine credits for query execution
* Charged based on actual compute resources used
* Depends on query complexity and execution time

#### Write Operations

* **Minimum 3 credits** per write operation
* Scales with data volume (GB written)
* Applied to INSERT, MERGE, CREATE TABLE AS SELECT, etc.

#### Storage Credits

* **4 credits per GB per month**
* Calculated based on end-of-day storage usage
* Encourages efficient data management and cleanup

#### Maintenance Operations

* OPTIMIZE, VACUUM, and ANALYZE operations consume credits
* Based on compute resources and data written during maintenance
* Can be automated with dbt post-hooks

<Note>
  A separate platform fee applies in addition to usage-based credits. See [Billing](/api-reference/overview/billing) for more details on credit pricing.
</Note>

## Best Practices

### Model Organization

```
models/
├── staging/           # Clean and standardize raw data
├── intermediate/      # Business logic transformations  
├── marts/            # Final datasets for analytics
└── utils/            # Reusable utility models
```

### Schema Organization

* Use `dev` target with personal suffixes during development
* Keep `prod` target for production deployments only
* Consider separate schemas for different projects or domains

### Performance Optimization

* Use incremental models for large datasets
* Partition by date fields when possible
* Add appropriate partitions via dbt configurations
* Run OPTIMIZE and VACUUM on large tables

### Credit Management

* Monitor credit usage in your Dune dashboard
* Use incremental models to reduce compute and write costs
* Drop unused development tables regularly
* Implement table lifecycle policies

### Data Management

* Clean up temporary/test data in `__tmp_` schemas
* Document table retention requirements
* Regularly review and optimize storage usage

### Version Control

* Store all transformation logic in Git
* Use meaningful commit messages
* Tag production releases
* Review PRs before merging to main

### Documentation

```yaml theme={null}
# schema.yml
models:
  - name: user_stats
    description: "Daily user trading statistics"
    columns:
      - name: user_address
        description: "Ethereum address of the user"
        tests:
          - not_null
          - unique
      - name: trade_count
        description: "Number of trades in the period"
```

## Resources

### Documentation

* [dbt Template Repository](https://github.com/duneanalytics/dune-dbt-template)
* [SQL Operations Reference](/api-reference/connectors/sql-operations)
* [Query Engine Overview](/query-engine/overview) - DuneSQL capabilities and read operations
* [Trino Connector](/api-reference/connectors/trino/overview) - General Trino connection guide
* [dbt Documentation](https://docs.getdbt.com/)
* [dbt-trino Setup Guide](https://docs.getdbt.com/docs/core/connect-data-platform/trino-setup)

### Support

* **Enterprise Support**: Contact your account team
* **GitHub Issues**: Report issues in the [template repository](https://github.com/duneanalytics/dune-dbt-template)

## Getting Started

Ready to get started? Clone the [template repository](https://github.com/duneanalytics/dune-dbt-template) and have your first dbt model running on Dune in minutes!

<CardGroup cols={2}>
  <Card title="dbt Template Repository" icon="github" href="https://github.com/duneanalytics/dune-dbt-template">
    Clone our official template to get started
  </Card>

  <Card title="Getting Started Guide" icon="rocket" href="/api-reference/connectors/dbt/getting-started">    Step-by-step setup instructions  </CardGroup>

This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.


> ## Documentation Index
>
> Fetch the complete documentation index at: https://docs.dune.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Billing

API access requires an active trial or a paid plan. Free access after a trial is view-only and does not include API exports, data writes, or alerts. Pricing for API usage is charged along several dimensions. All details can be found at [dune.com/pricing](https://dune.com/pricing).

<Note>
  Failed executions are not always charged. Queries that run until Dune's execution timeout, executions stopped by a user-defined resource/cost cap, and user-cancelled executions after compute has been used may consume credits for resources already used.

  Dune does not charge for SQL syntax/semantic errors, internal query-engine failures, or query-engine capacity-limit failures such as memory or stage limits. For a specific execution, check `execution_cost_credits` on the [status endpoint](/api-reference/executions/endpoint/get-execution-status).

## Executions

Credits are consumed based on actual compute resources used for each query execution. The performance tier you select affects credit consumption. If you execute a query but never pull the results, you are only charged for the execution.

## Data Export

Credits are consumed when exporting query results via API or CSV.


| Plan             | Credits per MB Exported |
| ------------------ | ------------------------- |
| Free (view-only) | Not available           |
| Analyst          | 10                      |
| Plus             | 2                       |
| Enterprise       | Custom                  |

## Data Writes

Credits are consumed when writing data (table creation, data insertion, uploads).


| Plan             | Credits per GB Written |
| ------------------ | ------------------------ |
| Free (view-only) | Not available          |
| Analyst          | 3                      |
| Plus             | 3                      |
| Enterprise       | Custom                 |

<Note>
  Minimum charge is 1 credit per write operation.
</Note>

## Storage

Storage limits are per-plan caps, not charged per-credit.


| Plan             | Storage Limit  |
| ------------------ | ---------------- |
| Free (view-only) | No data writes |
| Analyst          | 1 GB           |
| Plus             | 15 GB          |
| Enterprise       | Unlimited      |

## Webhooks (Alerts)


| Plan             | Webhooks      |
| ------------------ | --------------- |
| Free (view-only) | Not available |
| Analyst          | 5             |
| Plus             | 5             |
| Enterprise       | Custom        |

## Queries Endpoint

Available on Plus and Enterprise plans.

## Data Transformations Billing

Data Transformations is an Enterprise-only feature with usage-based credit consumption.

### Credit Consumption

#### Compute Credits

* Same as Fluid Engine credits for query execution
* Charged based on actual compute resources used
* Depends on query complexity and execution time

#### Write Operations

* **Minimum 1 credit** per write operation
* Scales with data volume (GB written)
* Applied to INSERT, MERGE, CREATE TABLE AS SELECT, etc.

#### Maintenance Operations

* OPTIMIZE, VACUUM, and ANALYZE operations consume credits
* Based on compute resources and data written during maintenance
* Can be automated with dbt post-hooks

See [dbt Connector documentation](/api-reference/connectors/dbt/overview) for more details.

This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.

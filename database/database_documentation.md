# TicketBlitz Supabase Database Schema 

---

## 1) Summary

### 1.1 What data is stored?
TicketBlitz data stores:
- Identity and authorization: `users`, `user_roles`
- Event catalog and inventory: `events`, `seat_categories`, `seats`, `inventory_event_state`
- Reservation workflow: `seat_holds`, `waitlist_entries`
- Payments and refunds: `transactions`, `payment_webhook_events`, `cancellation_requests`, `refund_attempts`
- Pricing and campaigns: `flash_sales`, `price_changes`
- Integration/outbox: `integration_events` 
- Reporting/read models: `v_waitlist_ranked`, `mv_sales_velocity_hourly`

### 1.2 Entity relationships
High-level cardinality:
- `events` 1:N `seat_categories`, `seats`, `seat_holds`, `waitlist_entries`, `transactions`, `flash_sales`, `price_changes`
- `seat_categories` 1:N `seats`, `seat_holds`, `waitlist_entries`, `price_changes`
- `seats` 1:N `seat_holds` (historical holds across time)
- `seat_holds` 1:N `transactions`, 1:N `waitlist_entries` , 1:N `cancellation_requests`
- `cancellation_requests` 1:N `refund_attempts`
- `users` 1:N across operational workflow tables


---

## 2) Current Exposed Schema Inventory

### 2.1 Base tables (15)
- `users`
- `events`
- `seat_categories`
- `seats`
- `seat_holds`
- `waitlist_entries`
- `transactions`
- `payment_webhook_events`
- `cancellation_requests`
- `refund_attempts`
- `flash_sales`
- `price_changes`
- `inventory_event_state`
- `integration_events` (partitioned)
- `user_roles`

### 2.2 Views/read models (2)
- `v_waitlist_ranked` (queue positions)
- `mv_sales_velocity_hourly` (hourly sales aggregate)

### 2.3 RPC functions (6)
- `inventory_create_hold`
- `inventory_confirm_hold`
- `inventory_release_hold`
- `inventory_expire_holds`
- `current_user_role`
- `is_current_user_organiser`

---
## Appendix A) Full Enum Matrix

| Enum Type | Values |
|---|---|
| `event_status_t` | `SCHEDULED`, `ACTIVE`, `FLASH_SALE_ACTIVE`, `CANCELLED`, `COMPLETED` |
| `seat_status_t` | `AVAILABLE`, `PENDING_WAITLIST`, `HELD`, `SOLD` |
| `hold_status_t` | `HELD`, `CONFIRMED`, `EXPIRED`, `RELEASED` |
| `hold_release_reason_t` | `PAYMENT_TIMEOUT`, `CANCELLATION`, `MANUAL_RELEASE`, `SYSTEM_CLEANUP` |
| `waitlist_status_t` | `WAITING`, `HOLD_OFFERED`, `CONFIRMED`, `EXPIRED`, `CANCELLED` |
| `transaction_status_t` | `PENDING`, `SUCCEEDED`, `FAILED`, `REFUND_PENDING`, `REFUND_SUCCEEDED`, `REFUND_FAILED` |
| `refund_attempt_status_t` | `PENDING`, `SUCCEEDED`, `FAILED` |
| `cancellation_status_t` | `REQUESTED`, `ELIGIBLE`, `REJECTED`, `PROCESSING_REFUND`, `REFUND_SUCCEEDED`, `REFUND_FAILED`, `CANCELLATION_IN_PROGRESS`, `COMPLETED` |
| `flash_sale_status_t` | `ACTIVE`, `ENDED`, `CANCELLED` |
| `price_change_reason_t` | `FLASH_SALE`, `ESCALATION`, `REVERT`, `MANUAL_ADJUSTMENT` |
| `app_role_t` | `fan`, `organiser` |

---

## Appendix B) Full Relation Data Dictionary 


### `users`
| Field name | PK/FK | Data type |
|---|---|---|
| user_id | PK | uuid |
| full_name | - | text |
| email | - | text |
| phone | - | text |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |
| deleted_at | - | timestamptz |
| search_vector | - | tsvector |
| auth_user_id | - | uuid |

### `events`
| Field name | PK/FK | Data type |
|---|---|---|
| event_id | PK | uuid |
| event_code | - | text |
| name | - | text |
| description | - | text |
| venue | - | text |
| event_date | - | timestamptz |
| booking_opens_at | - | timestamptz |
| booking_closes_at | - | timestamptz |
| total_capacity | - | integer |
| status | - | event_status_t |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |
| deleted_at | - | timestamptz |
| search_vector | - | tsvector |

### `seat_categories`
| Field name | PK/FK | Data type |
|---|---|---|
| category_id | PK | uuid |
| event_id | FK -> events.event_id | uuid |
| category_code | - | text |
| name | - | text |
| base_price | - | numeric |
| current_price | - | numeric |
| currency | - | char(3) |
| total_seats | - | integer |
| is_active | - | boolean |
| sort_order | - | smallint |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |
| deleted_at | - | timestamptz |

### `seats`
| Field name | PK/FK | Data type |
|---|---|---|
| seat_id | PK | uuid |
| event_id | FK -> events.event_id | uuid |
| category_id | FK -> seat_categories.category_id | uuid |
| seat_number | - | text |
| status | - | seat_status_t |
| version | - | integer |
| sold_at | - | timestamptz |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |

### `seat_holds`
| Field name | PK/FK | Data type |
|---|---|---|
| hold_id | PK | uuid |
| seat_id | FK -> seats.seat_id | uuid |
| event_id | FK -> events.event_id | uuid |
| category_id | FK -> seat_categories.category_id | uuid |
| user_id | FK -> users.user_id | uuid |
| from_waitlist | - | boolean |
| hold_expires_at | - | timestamptz |
| status | - | hold_status_t |
| release_reason | - | hold_release_reason_t |
| amount | - | numeric |
| currency | - | char(3) |
| idempotency_key | - | text |
| correlation_id | - | uuid |
| confirmed_at | - | timestamptz |
| released_at | - | timestamptz |
| expired_at | - | timestamptz |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |

### `waitlist_entries`
| Field name | PK/FK | Data type |
|---|---|---|
| waitlist_id | PK | uuid |
| event_id | FK -> events.event_id | uuid |
| category_id | FK -> seat_categories.category_id | uuid |
| user_id | FK -> users.user_id | uuid |
| hold_id | FK -> seat_holds.hold_id | uuid |
| status | - | waitlist_status_t |
| joined_at | - | timestamptz |
| offered_at | - | timestamptz |
| confirmed_at | - | timestamptz |
| expired_at | - | timestamptz |
| priority_score | - | numeric |
| source | - | text |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |

### `transactions`
| Field name | PK/FK | Data type |
|---|---|---|
| transaction_id | PK | uuid |
| hold_id | FK -> seat_holds.hold_id | uuid |
| event_id | FK -> events.event_id | uuid |
| user_id | FK -> users.user_id | uuid |
| amount | - | numeric |
| currency | - | char(3) |
| stripe_payment_intent_id | - | text |
| stripe_charge_id | - | text |
| status | - | transaction_status_t |
| failure_reason | - | text |
| refund_amount | - | numeric |
| refund_status | - | refund_attempt_status_t |
| refund_requested_at | - | timestamptz |
| refunded_at | - | timestamptz |
| idempotency_key | - | text |
| correlation_id | - | uuid |
| provider_response | - | jsonb |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |

### `payment_webhook_events`
| Field name | PK/FK | Data type |
|---|---|---|
| webhook_event_id | PK | text |
| payment_intent_id | - | text |
| hold_id | FK -> seat_holds.hold_id | uuid |
| event_type | - | text |
| payload | - | jsonb |
| received_at | - | timestamptz |
| processed_at | - | timestamptz |
| processing_status | - | text |
| error_message | - | text |

### `cancellation_requests`
| Field name | PK/FK | Data type |
|---|---|---|
| cancellation_request_id | PK | uuid |
| hold_id | FK -> seat_holds.hold_id | uuid |
| transaction_id | FK -> transactions.transaction_id | uuid |
| event_id | FK -> events.event_id | uuid |
| user_id | FK -> users.user_id | uuid |
| requested_at | - | timestamptz |
| policy_cutoff_at | - | timestamptz |
| is_policy_eligible | - | boolean |
| status | - | cancellation_status_t |
| reason | - | text |
| fee_percentage | - | numeric |
| refund_amount | - | numeric |
| attempt_count | - | integer |
| last_attempt_at | - | timestamptz |
| resolved_at | - | timestamptz |
| metadata | - | jsonb |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |

### `refund_attempts`
| Field name | PK/FK | Data type |
|---|---|---|
| refund_attempt_id | PK | uuid |
| cancellation_request_id | FK -> cancellation_requests.cancellation_request_id | uuid |
| transaction_id | FK -> transactions.transaction_id | uuid |
| attempt_no | - | integer |
| status | - | refund_attempt_status_t |
| provider_reference | - | text |
| error_code | - | text |
| error_message | - | text |
| provider_payload | - | jsonb |
| attempted_at | - | timestamptz |
| completed_at | - | timestamptz |
| created_at | - | timestamptz |

### `flash_sales`
| Field name | PK/FK | Data type |
|---|---|---|
| flash_sale_id | PK | uuid |
| event_id | FK -> events.event_id | uuid |
| discount_percentage | - | numeric |
| escalation_percentage | - | numeric |
| starts_at | - | timestamptz |
| ends_at | - | timestamptz |
| status | - | flash_sale_status_t |
| launched_by_user_id | FK -> users.user_id | uuid |
| config | - | jsonb |
| ended_at | - | timestamptz |
| created_at | - | timestamptz |
| updated_at | - | timestamptz |
| active_window | - | tstzrange |

### `price_changes`
| Field name | PK/FK | Data type |
|---|---|---|
| change_id | PK | uuid |
| flash_sale_id | FK -> flash_sales.flash_sale_id | uuid |
| event_id | FK -> events.event_id | uuid |
| category_id | FK -> seat_categories.category_id | uuid |
| reason | - | price_change_reason_t |
| old_price | - | numeric |
| new_price | - | numeric |
| changed_at | - | timestamptz |
| changed_by | - | text |
| context | - | jsonb |
| created_at | - | timestamptz |

### `inventory_event_state`
| Field name | PK/FK | Data type |
|---|---|---|
| event_id | PK, FK -> events.event_id | uuid |
| flash_sale_active | - | boolean |
| active_flash_sale_id | FK -> flash_sales.flash_sale_id | uuid |
| last_sold_out_category | - | text |
| last_sold_out_at | - | timestamptz |
| metadata | - | jsonb |
| updated_at | - | timestamptz |

### `integration_events` (partitioned)
| Field name | PK/FK | Data type |
|---|---|---|
| event_id | PK (part) | uuid |
| occurred_at | PK (part) | timestamptz |
| producer_service | - | text |
| aggregate_type | - | text |
| aggregate_id | - | uuid |
| event_name | - | text |
| exchange_name | - | text |
| routing_key | - | text |
| payload | - | jsonb |
| headers | - | jsonb |
| waitlist_emails | - | text[] |
| published | - | boolean |
| published_at | - | timestamptz |
| publish_error | - | text |

### `user_roles`
| Field name | PK/FK | Data type |
|---|---|---|
| user_id | PK (exposed metadata), FK -> users.user_id | uuid |
| role | - | app_role_t |
| assigned_at | - | timestamptz |
| assigned_by | FK -> users.user_id | uuid |

### `v_waitlist_ranked` (view)
| Field name | PK/FK | Data type |
|---|---|---|
| waitlist_id | - | uuid |
| event_id | FK -> events.event_id | uuid |
| category_id | FK -> seat_categories.category_id | uuid |
| user_id | FK -> users.user_id | uuid |
| status | - | waitlist_status_t |
| joined_at | - | timestamptz |
| queue_position | - | bigint |

### `mv_sales_velocity_hourly` (materialized view)
| Field name | PK/FK | Data type |
|---|---|---|
| event_id | FK -> events.event_id | uuid |
| category_id | FK -> seat_categories.category_id | uuid |
| hour_bucket | - | timestamptz |
| successful_payment_count | - | bigint |
| gross_sales_amount | - | numeric |

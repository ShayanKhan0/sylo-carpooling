# Payments API Reference

**Base URL:** `/api/v1/payments`  
**Authentication:** JWT Bearer Token Required  
**Version:** 1.0  
**Last Updated:** 2025-11-08

---

## 📚 Table of Contents
1. [Wallet Endpoints](#wallet-endpoints)
2. [Transaction Endpoints](#transaction-endpoints)
3. [Payout Endpoints](#payout-endpoints)
4. [Webhook Endpoints](#webhook-endpoints)
5. [Commission Calculation](#commission-calculation)
6. [Error Codes](#error-codes)
7. [Testing Examples](#testing-examples)

---

## 🪙 Wallet Endpoints

### 1. Create Wallet
**Endpoint:** `POST /wallet/create`  
**Status Code:** 201 Created  
**Description:** Create new wallet for user (auto-created during registration)

**Request Body:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "initial_balance": 0.00,
  "currency": "PKR"
}
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "id": "987e6543-e21b-12d3-a456-426614174111",
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "balance": 0.00,
    "currency": "PKR",
    "created_at": "2025-11-08T10:00:00Z",
    "last_updated": "2025-11-08T10:00:00Z"
  },
  "error": null
}
```

**Business Rules:**
- One wallet per user (unique constraint)
- Initial balance defaults to 0.00 PKR
- Currency code must be 3 characters (ISO 4217)

---

### 2. Get Wallet Balance
**Endpoint:** `GET /wallet/balance/{user_id}`  
**Status Code:** 200 OK  
**Description:** Get current wallet balance

**Path Parameters:**
- `user_id` (UUID, required): User ID

**Response:**
```json
{
  "status": "ok",
  "data": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "balance": 1250.50,
    "currency": "PKR",
    "last_updated": "2025-11-08T15:30:00Z"
  },
  "error": null
}
```

**Authorization:** User can only view own balance (unless admin)

---

### 3. Top-Up Wallet
**Endpoint:** `POST /wallet/topup`  
**Status Code:** 200 OK  
**Description:** Add funds to wallet via payment provider

**Request Body:**
```json
{
  "amount": 500.00,
  "provider": "jazzcash",
  "provider_txn_id": "JC202511081234567",
  "description": "Wallet top-up via JazzCash"
}
```

**Supported Providers:**
- `jazzcash` - JazzCash mobile wallet (Pakistan)
- `easypaisa` - EasyPaisa mobile wallet (Pakistan)
- `stripe` - Stripe payment gateway
- `paypal` - PayPal
- `mock` - Mock provider for testing

**Success Response:**
```json
{
  "status": "ok",
  "data": {
    "success": true,
    "message": "Top-up successful",
    "transaction_id": "TXN-20251108-ABC123",
    "wallet_balance": 1750.50,
    "amount_added": 500.00
  },
  "error": null
}
```

**Error Response:**
```json
{
  "status": "error",
  "data": null,
  "error": "Payment declined by provider"
}
```

**Validation:**
- Amount must be positive
- Amount limited to 2 decimal places
- Provider must be configured with API keys

**Process Flow:**
1. Validate payment provider
2. Create pending transaction
3. Process payment with provider
4. Update wallet balance if successful
5. Update transaction status

---

### 4. Deduct from Wallet
**Endpoint:** `POST /wallet/deduct`  
**Status Code:** 200 OK  
**Description:** Deduct funds from wallet (ride payments, fees)

**Request Body:**
```json
{
  "amount": 150.00,
  "ride_id": "abc12345-e89b-12d3-a456-426614174222",
  "description": "Payment for ride #12345",
  "metadata": {
    "driver_share": 120.00,
    "platform_commission": 30.00
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "success": true,
    "message": "Deduction successful",
    "transaction_id": "TXN-20251108-XYZ789",
    "wallet_balance": 1100.50,
    "amount_deducted": 150.00
  },
  "error": null
}
```

**Validation:**
- Checks sufficient balance before deduction
- Amount must be positive
- Creates transaction record for audit trail

**Use Cases:**
- Ride payment
- Platform fees
- Cancellation charges

---

## 📋 Transaction Endpoints

### 5. Get Transaction History
**Endpoint:** `GET /wallet/transactions`  
**Status Code:** 200 OK  
**Description:** Get user transaction history with pagination and filters

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `type` | string | No | Filter by transaction type |
| `status` | string | No | Filter by status |
| `limit` | integer | No | Records per page (1-100, default 20) |
| `offset` | integer | No | Pagination offset (default 0) |

**Transaction Types:**
- `topup` - User added funds
- `deduct` - Platform deducted funds
- `refund` - Funds returned to user
- `payout` - Driver earnings payout
- `commission` - Driver commission credit
- `bonus` - Promotional credits

**Transaction Statuses:**
- `pending` - Initiated, awaiting confirmation
- `processing` - Being processed
- `completed` - Successfully completed
- `failed` - Failed
- `reversed` - Reversed/rolled back

**Example Request:**
```
GET /api/v1/payments/wallet/transactions?type=topup&status=completed&limit=10&offset=0
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "transactions": [
      {
        "id": "111e2222-e33b-44d5-a666-777777777777",
        "txn_id": "TXN-20251108-ABC123",
        "wallet_id": "987e6543-e21b-12d3-a456-426614174111",
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "amount": 500.00,
        "type": "topup",
        "status": "completed",
        "ride_id": null,
        "payout_id": null,
        "provider": "jazzcash",
        "provider_txn_id": "JC202511081234567",
        "description": "Wallet top-up via JazzCash",
        "created_at": "2025-11-08T10:00:00Z",
        "updated_at": "2025-11-08T10:00:30Z",
        "completed_at": "2025-11-08T10:00:30Z"
      }
    ],
    "total_count": 25,
    "page": 1,
    "page_size": 10
  },
  "error": null
}
```

**Performance:**
- Indexed queries (user_id, type, status, created_at)
- Ordered by created_at DESC
- Pagination recommended for large datasets

---

## 💸 Payout Endpoints

### 6. Request Payout
**Endpoint:** `POST /payout/request`  
**Status Code:** 201 Created  
**Description:** Request driver payout to bank account or mobile wallet

**Request Body:**
```json
{
  "amount": 2500.00,
  "method": "jazzcash",
  "account_details": "03001234567",
  "notes": "Weekly earnings payout"
}
```

**Payout Methods:**
- `bank_transfer` - Direct bank transfer
- `jazzcash` - JazzCash mobile wallet (03XX-XXXXXXX format)
- `easypaisa` - EasyPaisa mobile wallet (03XX-XXXXXXX format)
- `stripe` - Stripe Connect
- `paypal` - PayPal transfer

**Response:**
```json
{
  "status": "ok",
  "data": {
    "id": "888e9999-e00a-11b2-c333-444444444444",
    "driver_id": "555e6666-e77b-88d9-a000-111111111111",
    "amount": 2500.00,
    "method": "jazzcash",
    "account_details": "*******4567",
    "status": "pending",
    "provider": null,
    "provider_payout_id": null,
    "created_at": "2025-11-08T16:00:00Z",
    "updated_at": "2025-11-08T16:00:00Z",
    "processed_at": null,
    "completed_at": null,
    "notes": "Weekly earnings payout"
  },
  "error": null
}
```

**Requirements:**
- Minimum amount: **500 PKR**
- Driver must be verified
- Sufficient wallet balance
- Valid payment method details

**Account Details Validation:**
- **Bank Transfer:** Digits, spaces, dashes only
- **JazzCash/EasyPaisa:** 11-digit Pakistani mobile (03XX-XXXXXXX)

**Security:**
- Account details **masked** in response (last 4 digits only)
- Rate limiting applied
- Fraud detection for unusual patterns

**Payout Process:**
1. Validate driver and balance
2. Create payout record (status: PENDING)
3. Deduct from driver wallet
4. Queue for processing
5. Transfer to payment provider
6. Update status (COMPLETED/FAILED)

---

### 7. Get Payout History
**Endpoint:** `GET /payout/history`  
**Status Code:** 200 OK  
**Description:** Get driver payout history

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter by payout status |
| `limit` | integer | No | Records per page (1-100, default 20) |
| `offset` | integer | No | Pagination offset (default 0) |

**Payout Statuses:**
- `pending` - Requested, awaiting processing
- `processing` - Being transferred
- `completed` - Successfully transferred
- `failed` - Transfer failed
- `cancelled` - Payout cancelled

**Response:**
```json
{
  "status": "ok",
  "data": {
    "payouts": [
      {
        "id": "888e9999-e00a-11b2-c333-444444444444",
        "driver_id": "555e6666-e77b-88d9-a000-111111111111",
        "amount": 2500.00,
        "method": "jazzcash",
        "account_details": "*******4567",
        "status": "completed",
        "provider": "jazzcash_api",
        "provider_payout_id": "JC_PAYOUT_20251108_XYZ789",
        "created_at": "2025-11-08T16:00:00Z",
        "updated_at": "2025-11-08T16:05:00Z",
        "processed_at": "2025-11-08T16:02:00Z",
        "completed_at": "2025-11-08T16:05:00Z",
        "notes": "Weekly earnings payout"
      }
    ],
    "total_count": 8,
    "page": 1,
    "page_size": 20
  },
  "error": null
}
```

---

## 🔔 Webhook Endpoints

### 8. Payment Webhook Verification
**Endpoint:** `POST /webhook/verify`  
**Status Code:** 200 OK  
**Description:** Verify and process payment provider webhooks

**Request Body:**
```json
{
  "provider": "jazzcash",
  "event_type": "payment.success",
  "txn_id": "TXN-20251108-ABC123",
  "provider_txn_id": "JC202511081234567",
  "amount": 500.00,
  "status": "completed",
  "signature": "a1b2c3d4e5f6...",
  "payload": {
    "transaction_id": "JC202511081234567",
    "amount": "500.00",
    "currency": "PKR",
    "status": "SUCCESS",
    "timestamp": "2025-11-08T10:00:30Z"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "message": "Webhook processed successfully"
  },
  "error": null
}
```

**Security:**
- **Signature verification** using HMAC-SHA256
- Validates webhook authenticity
- Prevents replay attacks

**Process:**
1. Verify webhook signature
2. Extract transaction ID and status
3. Update transaction record
4. Update wallet balance if needed
5. Send confirmation to provider

**Note:** This endpoint typically called by **payment providers**, not clients.

---

## 💰 Commission Calculation

### Default Configuration
- **Platform Commission:** 20%
- **Driver Share:** 80%
- **Minimum Driver Share:** 50% (enforced)

### Formula
```
platform_commission = total_fare × (commission_rate / 100)
driver_share = total_fare - platform_commission

# Constraints:
- commission_rate: 5% - 50%
- driver_share: minimum 50% of total_fare
- All amounts rounded to 2 decimal places
```

### Examples

#### Example 1: Default 20% Commission
```
Total Fare: 150.00 PKR
Platform Commission: 150.00 × 0.20 = 30.00 PKR
Driver Share: 150.00 - 30.00 = 120.00 PKR
```

#### Example 2: Custom 15% Commission
```
Total Fare: 200.00 PKR
Platform Commission: 200.00 × 0.15 = 30.00 PKR
Driver Share: 200.00 - 30.00 = 170.00 PKR
```

#### Example 3: Minimum Driver Share Protection
```
Total Fare: 100.00 PKR
Requested Commission: 60% (60.00 PKR)
Driver Share: Would be 40.00 PKR

❌ Rejected - Driver share below 50%
✅ Adjusted - Driver share = 50.00 PKR, Commission = 50.00 PKR
```

### API Endpoint for Commission Calculation
```python
from .utils import calculate_commission
from decimal import Decimal

split = calculate_commission(
    amount=Decimal("150.00"),
    commission_rate=Decimal("20.0")
)

# Result:
{
    "total_fare": Decimal("150.00"),
    "driver_share": Decimal("120.00"),
    "platform_commission": Decimal("30.00"),
    "commission_percentage": Decimal("20.0")
}
```

---

## ⚠️ Error Codes

| Status Code | Error | Description |
|-------------|-------|-------------|
| **400** | Bad Request | Invalid input, insufficient balance, validation error |
| **401** | Unauthorized | Invalid or missing JWT token, invalid webhook signature |
| **403** | Forbidden | User not authorized for this operation |
| **404** | Not Found | Wallet, transaction, or payout not found |
| **500** | Internal Server Error | Database error, provider error, server failure |

### Common Error Responses

#### Insufficient Balance
```json
{
  "detail": "Insufficient balance. Available: 100.50, Required: 150.00"
}
```

#### Wallet Not Found
```json
{
  "detail": "Wallet not found"
}
```

#### Invalid Provider
```json
{
  "detail": "Unsupported payment provider: unknown. Supported: jazzcash, easypaisa, stripe, paypal, mock"
}
```

#### Payout Minimum Not Met
```json
{
  "detail": "Minimum payout amount is 500 PKR"
}
```

#### Invalid Webhook Signature
```json
{
  "detail": "Invalid webhook signature"
}
```

---

## 🧪 Testing Examples

### Using cURL

#### 1. Get Wallet Balance
```bash
curl -X GET "http://localhost:8000/api/v1/payments/wallet/balance/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

#### 2. Top-Up Wallet
```bash
curl -X POST "http://localhost:8000/api/v1/payments/wallet/topup" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 500.00,
    "provider": "mock",
    "description": "Test top-up"
  }'
```

#### 3. Get Transaction History
```bash
curl -X GET "http://localhost:8000/api/v1/payments/wallet/transactions?limit=10&type=topup" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

#### 4. Request Payout
```bash
curl -X POST "http://localhost:8000/api/v1/payments/payout/request" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 1000.00,
    "method": "jazzcash",
    "account_details": "03001234567",
    "notes": "Test payout"
  }'
```

### Using Python Requests

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/payments"
TOKEN = "your_jwt_token_here"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Top-up wallet
response = requests.post(
    f"{BASE_URL}/wallet/topup",
    headers=HEADERS,
    json={
        "amount": 500.00,
        "provider": "mock",
        "description": "Test top-up"
    }
)
print(response.json())

# Get balance
response = requests.get(
    f"{BASE_URL}/wallet/balance/YOUR_USER_ID",
    headers=HEADERS
)
print(response.json())

# Get transactions
response = requests.get(
    f"{BASE_URL}/wallet/transactions?limit=5",
    headers=HEADERS
)
print(response.json())
```

---

## 📊 Best Practices

### 1. Always Validate Balance Before Operations
```python
balance = await get_wallet_balance(db, user_id)
if balance < required_amount:
    raise HTTPException(status_code=400, detail="Insufficient balance")
```

### 2. Use Atomic Transactions
```python
async with db.begin():
    await update_wallet_balance(db, wallet_id, amount, "subtract")
    await log_transaction(db, transaction_data)
```

### 3. Handle Provider Failures Gracefully
```python
try:
    response = await payment_provider.process(amount)
except ProviderError as e:
    await update_transaction_status(db, txn_id, TransactionStatusEnum.FAILED)
    raise HTTPException(status_code=502, detail="Provider unavailable")
```

### 4. Verify Webhooks Always
```python
if not verify_signature(payload, signature, provider):
    raise HTTPException(status_code=401, detail="Invalid signature")
```

### 5. Mask Sensitive Data in Responses
```python
payout.account_details = mask_account_details(payout.account_details)
```

### 6. Use Pagination for History Queries
```python
# Good: Limited results
transactions = await get_user_transactions(db, user_id, limit=20, offset=0)

# Bad: Unlimited results (memory issues)
# transactions = await get_all_transactions(db, user_id)
```

---

## 🔗 Related Endpoints

- **Authentication:** `/api/v1/auth/*` - Get JWT tokens
- **Users:** `/api/v1/users/*` - User profile management
- **Drivers:** `/api/v1/drivers/*` - Driver profile and earnings
- **Rides:** `/api/v1/rides/*` - Ride management (triggers payments)
- **Admin:** `/api/v1/admin/*` - Admin payment management

---

**API Version:** 1.0  
**Last Updated:** 2025-11-08  
**Maintained By:** Smart Carpooling Development Team
# 完整契约示例

> 一个含增删改查 + 分页 + 幂等的完整示例。可参考仓库内 `examples/petstore.yaml`(最简版)。

```yaml
openapi: 3.0.3
info:
  title: Pet Order Service
  version: 1.0.0

paths:
  /pet-orders:
    get:
      operationId: listPetOrders
      parameters:
        - name: page
          in: query
          schema: { type: integer, minimum: 1, default: 1 }
        - name: pageSize
          in: query
          schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: array
                items: { $ref: '#/components/schemas/PetOrder' }
    post:
      operationId: createPetOrder
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreatePetOrderRequest' }
      responses:
        '201':
          description: created
          content:
            application/json:
              schema: { $ref: '#/components/schemas/PetOrder' }

  /pet-orders/{orderId}:
    get:
      operationId: getPetOrderById
      parameters:
        - name: orderId
          in: path
          required: true
          schema: { type: string }
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema: { $ref: '#/components/schemas/PetOrder' }
        '404':
          description: not found
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Error' }

components:
  schemas:
    PetOrder:
      type: object
      required: [id, status, petId, createdAt]
      properties:
        id: { type: string }
        petId: { type: string }
        status: { type: string, enum: [PENDING, CONFIRMED, SHIPPED, CANCELLED] }
        createdAt: { type: string, format: date-time }
    CreatePetOrderRequest:
      type: object
      required: [petId]
      properties:
        petId: { type: string }
        remark: { type: string }
    Error:
      type: object
      required: [code, message]
      properties:
        code: { type: string }
        message: { type: string }
        details: { type: object }
```

## 设计要点

1. 资源用名词复数 `/pet-orders`
2. 读操作用 GET 返回对象或数组;写操作用 POST + `XxxRequest` DTO
3. 状态字段用 `enum`,错误统一 `Error` schema
4. 分页用 `page` / `pageSize` 查询参数;幂等用 `Idempotency-Key` 头

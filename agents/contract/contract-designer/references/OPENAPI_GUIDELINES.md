# OpenAPI 设计规范

> 契约是前后端唯一事实源(SSOT),设计质量直接决定生成代码与一致性门控的效果。

## 命名约定

| 元素 | 约定 | 示例 |
|------|------|------|
| path | kebab-case、名词复数 | `/pet-orders` |
| operationId | camelCase、动词+资源 | `listPetOrders` / `createPetOrder` |
| schema 名 | PascalCase | `PetOrder` / `CreatePetOrderRequest` |
| 字段名 | camelCase | `createdAt` / `orderStatus` |
| 枚举值 | UPPER_SNAKE | `PENDING` / `SHIPPED` |

## Schema 设计

1. **必填最小化**:`required` 只列真正必须的字段,其余可选
2. **类型准确**:`integer`(整数)/`number`(浮点)/`string`/`boolean`/`array`/`object`
3. **$ref 优先**:可复用的 DTO 用 `$ref` 引用 `#/components/schemas/`,避免内联重复
4. **枚举用 enum**:状态 / 类型字段用 `enum` 而非裸 string
5. **date-time 用 format**:时间字段 `type: string, format: date-time`

## 请求 / 响应约定

- 写操作(POST/PUT/PATCH)requestBody 用 `$ref` 指向 `XxxRequest` DTO
- 读操作(GET)响应为对象或 `array`(items 用 `$ref`)
- 错误响应统一 `Error` schema:`{ code, message, details? }`

## 分页约定(x-*)

```yaml
parameters:
  - name: page
    in: query
    schema: { type: integer, minimum: 1, default: 1 }
    x-page: true
  - name: pageSize
    in: query
    schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
    x-page-size: true
```

## 错误码约定

| code | 语义 |
|------|------|
| 400 | 参数校验失败 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突(如重复创建) |
| 422 | 业务校验失败 |
| 500 | 服务端错误 |

## 幂等约定(x-*)

写操作默认要求幂等键:

```yaml
post:
  parameters:
    - name: Idempotency-Key
      in: header
      required: true
      x-idempotency-key: true
```

## 自检清单

- [ ] 每个操作有 operationId
- [ ] 每个 schema 有 `type` 与 `required`
- [ ] 写操作有 requestBody,$ref 引用命名 schema
- [ ] 成功响应有 2xx + application/json schema
- [ ] 可被 `python3 -c "from lib.contract.parser import parse_contract; parse_contract('<file>')"` 解析

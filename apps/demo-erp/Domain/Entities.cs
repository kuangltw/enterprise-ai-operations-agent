namespace EnterpriseDemoErp.Domain;

// M1 最小資料模型；不包含採購業務邏輯。
public sealed class Product
{
    public Guid Id { get; set; }
    public string Sku { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public bool IsActive { get; set; } = true;
}

public sealed class Warehouse
{
    public Guid Id { get; set; }
    public string Code { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
}

public sealed class Inventory
{
    public Guid WarehouseId { get; set; }
    public Guid ProductId { get; set; }
    public decimal OnHand { get; set; }
    public decimal Reserved { get; set; }
    public long RowVersion { get; set; }
}

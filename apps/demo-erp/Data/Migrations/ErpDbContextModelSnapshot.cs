using System;
using EnterpriseDemoErp.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

#nullable disable

namespace EnterpriseDemoErp.Data.Migrations;

[DbContext(typeof(ErpDbContext))]
public partial class ErpDbContextModelSnapshot : ModelSnapshot
{
    protected override void BuildModel(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity("EnterpriseDemoErp.Domain.Product", b =>
        {
            b.Property<Guid>("Id").ValueGeneratedNever();
            b.Property<bool>("IsActive");
            b.Property<string>("Name").IsRequired().HasMaxLength(200);
            b.Property<string>("Sku").IsRequired().HasMaxLength(80);
            b.HasKey("Id");
            b.HasIndex("Sku").IsUnique();
            b.ToTable("erp_products");
        });
        modelBuilder.Entity("EnterpriseDemoErp.Domain.Warehouse", b =>
        {
            b.Property<Guid>("Id").ValueGeneratedNever();
            b.Property<string>("Code").IsRequired().HasMaxLength(50);
            b.Property<string>("Name").IsRequired().HasMaxLength(200);
            b.HasKey("Id");
            b.HasIndex("Code").IsUnique();
            b.ToTable("erp_warehouses");
        });
        modelBuilder.Entity("EnterpriseDemoErp.Domain.Inventory", b =>
        {
            b.Property<Guid>("WarehouseId");
            b.Property<Guid>("ProductId");
            b.Property<decimal>("OnHand").HasPrecision(14, 3);
            b.Property<decimal>("Reserved").HasPrecision(14, 3);
            b.Property<long>("RowVersion").IsConcurrencyToken();
            b.HasKey("WarehouseId", "ProductId");
            b.HasIndex("ProductId");
            b.ToTable("erp_inventory");
            b.HasOne("EnterpriseDemoErp.Domain.Product", null)
                .WithMany().HasForeignKey("ProductId").OnDelete(DeleteBehavior.Cascade);
            b.HasOne("EnterpriseDemoErp.Domain.Warehouse", null)
                .WithMany().HasForeignKey("WarehouseId").OnDelete(DeleteBehavior.Cascade);
        });
    }
}

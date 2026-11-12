using EnterpriseDemoErp.Domain;
using Microsoft.EntityFrameworkCore;

namespace EnterpriseDemoErp.Data;

public sealed class ErpDbContext(DbContextOptions<ErpDbContext> options) : DbContext(options)
{
    public DbSet<Product> Products => Set<Product>();
    public DbSet<Warehouse> Warehouses => Set<Warehouse>();
    public DbSet<Inventory> Inventories => Set<Inventory>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Product>(entity =>
        {
            entity.ToTable("erp_products");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Sku).HasMaxLength(80).IsRequired();
            entity.Property(e => e.Name).HasMaxLength(200).IsRequired();
            entity.HasIndex(e => e.Sku).IsUnique();
        });

        modelBuilder.Entity<Warehouse>(entity =>
        {
            entity.ToTable("erp_warehouses");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Code).HasMaxLength(50).IsRequired();
            entity.Property(e => e.Name).HasMaxLength(200).IsRequired();
            entity.HasIndex(e => e.Code).IsUnique();
        });

        modelBuilder.Entity<Inventory>(entity =>
        {
            entity.ToTable("erp_inventory");
            entity.HasKey(e => new { e.WarehouseId, e.ProductId });
            entity.Property(e => e.OnHand).HasPrecision(14, 3);
            entity.Property(e => e.Reserved).HasPrecision(14, 3);
            entity.Property(e => e.RowVersion).IsConcurrencyToken();
            entity.HasOne<Warehouse>().WithMany().HasForeignKey(e => e.WarehouseId);
            entity.HasOne<Product>().WithMany().HasForeignKey(e => e.ProductId);
        });
    }
}

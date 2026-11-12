using System;
using EnterpriseDemoErp.Data;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseDemoErp.Data.Migrations;

[DbContext(typeof(ErpDbContext))]
[Migration("202611120001_InitialErp")]
public partial class InitialErp : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "erp_products",
            columns: table => new
            {
                Id = table.Column<Guid>(type: "uuid", nullable: false),
                Sku = table.Column<string>(type: "character varying(80)", maxLength: 80, nullable: false),
                Name = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                IsActive = table.Column<bool>(type: "boolean", nullable: false)
            },
            constraints: table => table.PrimaryKey("PK_erp_products", x => x.Id));

        migrationBuilder.CreateTable(
            name: "erp_warehouses",
            columns: table => new
            {
                Id = table.Column<Guid>(type: "uuid", nullable: false),
                Code = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                Name = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false)
            },
            constraints: table => table.PrimaryKey("PK_erp_warehouses", x => x.Id));

        migrationBuilder.CreateTable(
            name: "erp_inventory",
            columns: table => new
            {
                WarehouseId = table.Column<Guid>(type: "uuid", nullable: false),
                ProductId = table.Column<Guid>(type: "uuid", nullable: false),
                OnHand = table.Column<decimal>(type: "numeric(14,3)", nullable: false),
                Reserved = table.Column<decimal>(type: "numeric(14,3)", nullable: false),
                RowVersion = table.Column<long>(type: "bigint", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_erp_inventory", x => new { x.WarehouseId, x.ProductId });
                table.ForeignKey("FK_erp_inventory_erp_products_ProductId", x => x.ProductId,
                    "erp_products", "Id", onDelete: ReferentialAction.Cascade);
                table.ForeignKey("FK_erp_inventory_erp_warehouses_WarehouseId", x => x.WarehouseId,
                    "erp_warehouses", "Id", onDelete: ReferentialAction.Cascade);
            });
        migrationBuilder.CreateIndex("IX_erp_products_Sku", "erp_products", "Sku", unique: true);
        migrationBuilder.CreateIndex("IX_erp_warehouses_Code", "erp_warehouses", "Code", unique: true);
        migrationBuilder.CreateIndex("IX_erp_inventory_ProductId", "erp_inventory", "ProductId");
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropTable("erp_inventory");
        migrationBuilder.DropTable("erp_products");
        migrationBuilder.DropTable("erp_warehouses");
    }
}

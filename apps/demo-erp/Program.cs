using EnterpriseDemoErp.Data;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
var connectionString = builder.Configuration.GetConnectionString("ErpDb")
    ?? throw new InvalidOperationException("尚未設定 ERP 資料庫連線。");

builder.Services.AddDbContext<ErpDbContext>(options =>
    options.UseNpgsql(connectionString));

builder.Services.AddHealthChecks().AddDbContextCheck<ErpDbContext>();

var app = builder.Build();

// M1 僅建置資料模型及健康檢查；尚未開放採購寫入或未授權業務 API。
// Migration 在啟動時套用，正式環境應改由 CI/CD 獨立 Migration Job 執行。
using (var scope = app.Services.CreateScope())
{
    var database = scope.ServiceProvider.GetRequiredService<ErpDbContext>();
    await database.Database.MigrateAsync();
}

app.MapGet("/health/live", () => Results.Ok(new
{
    status = "ok",
    service = "demo-erp"
})).AllowAnonymous();

app.MapHealthChecks("/health/ready").AllowAnonymous();

app.Run();

public partial class Program { }

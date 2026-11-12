FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY EnterpriseDemoErp.csproj .
RUN dotnet restore EnterpriseDemoErp.csproj
COPY . .
RUN dotnet publish EnterpriseDemoErp.csproj -c Release -o /out --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /out .
EXPOSE 8080
ENTRYPOINT ["dotnet", "EnterpriseDemoErp.dll"]


# Deploy To Web App

```
az webapp deploy \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<APP_SERVICE_NAME>" \
  --src-path "mcp_server/dist/gds-mcp-appservice.zip" \
  --type zip \
  --restart true \
  --track-status true
```
az webapp deploy \
  --resource-group "gds_etl_workbench" \
  --name "gds-test-workbench" \
  --src-path "mcp_server/dist/gds-mcp-appservice.zip" \
  --type zip \
  --restart true \
  --track-status true
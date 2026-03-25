#Requires -Version 5.1
<#
.SYNOPSIS
    Create Azure AI Search index for SecondCortex snapshots
.PARAMETER searchServiceName
    Name of the Azure Search service
.PARAMETER apiKey
    Admin API key for the search service
.PARAMETER indexName
    Name of the index (default: "snapshots")
.EXAMPLE
    .\create-search-index.ps1 -searchServiceName "secondcortex-search" -apiKey "your-api-key"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$searchServiceName,

    [Parameter(Mandatory=$true)]
    [string]$apiKey,

    [Parameter(Mandatory=$false)]
    [string]$indexName = "snapshots"
)

$endpoint = "https://$searchServiceName.search.windows.net"

# Index schema definition
$indexSchema = @{
    name = $indexName
    fields = @(
        @{ name = "id"; type = "Edm.String"; key = $true; retrievable = $true }
        @{ name = "user_id"; type = "Edm.String"; retrievable = $true; filterable = $true }
        @{ name = "project_id"; type = "Edm.String"; retrievable = $true; filterable = $true }
        @{ name = "summary"; type = "Edm.String"; searchable = $true; retrievable = $true }
        @{ name = "active_file"; type = "Edm.String"; retrievable = $true }
        @{ name = "git_branch"; type = "Edm.String"; retrievable = $true }
        @{ name = "timestamp"; type = "Edm.DateTimeOffset"; retrievable = $true; filterable = $true; sortable = $true }
        @{ name = "entities"; type = "Edm.String"; retrievable = $true }
        @{ 
            name = "embedding"
            type = "Collection(Edm.Single)"
            retrievable = $true
            searchable = $true
            dimensions = 1536
            vectorSearchConfiguration = "default"
        }
    )
    vectorSearch = @{
        algorithms = @(
            @{ name = "default"; kind = "hnsw" }
        )
        profiles = @(
            @{ 
                name = "default"
                algorithm = "default"
                vectorizer = "default"
            }
        )
        vectorizers = @(
            @{ 
                name = "default"
                kind = "AzureOpenAI"
                azureOpenAIParameters = @{
                    resourceUri = "https://<your-openai-resource>.openai.azure.com/"
                    apiKey = "<your-openai-key>"
                    modelName = "text-embedding-3-small"
                }
            }
        )
    }
    semantic = @{
        configurations = @(
            @{
                name = "default"
                prioritizedFields = @{
                    titleField = @{ fieldName = "summary" }
                    contentFields = @(
                        @{ fieldName = "active_file" }
                        @{ fieldName = "entities" }
                    )
                    keywordsFields = @(
                        @{ fieldName = "git_branch" }
                    )
                }
            }
        )
    }
} | ConvertTo-Json -Depth 10

Write-Host "Creating index '$indexName' in search service '$searchServiceName'..." -ForegroundColor Cyan

$response = Invoke-RestMethod `
    -Uri "$endpoint/indexes/$($indexName)?api-version=2024-07-01" `
    -Method Put `
    -Headers @{
        "api-key" = $apiKey
        "Content-Type" = "application/json"
    } `
    -Body $indexSchema

Write-Host "✓ Index created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Index Details:" -ForegroundColor Green
Write-Host "  Name: $($response.name)"
Write-Host "  Fields: $($response.fields.Count)"
Write-Host "  Vector Search: Enabled (HnswAlgorithm)"
Write-Host "  Semantic Search: Enabled"
Write-Host ""
Write-Host "⚠ IMPORTANT: Update vectorizer configuration!" -ForegroundColor Yellow
Write-Host ""
Write-Host "The index was created with placeholder Azure OpenAI credentials."
Write-Host "You MUST update the vectorizer with actual credentials:"
Write-Host ""
Write-Host "1. In Azure Portal:"
Write-Host "   - Navigate to Cognitive Search > Indexes > $indexName > Fields > embedding"
Write-Host "   - Update azureOpenAIParameters with your actual credentials"
Write-Host ""
Write-Host "2. Or via Azure CLI:"
Write-Host "   az search index update --service-name $searchServiceName --index-name $indexName --index-file index-schema.json"
Write-Host ""

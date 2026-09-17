## download goose install-script
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/aaif-goose/goose/main/download_cli.ps1" -OutFile "download_cli.ps1";
## run the downloaded powershell script to install goose
.\download_cli.ps1

## get an api key from 
https://openrouter.ai/workspaces/default/keys
https://openrouter.ai/openrouter/free

## add goose installation location to env-var
[Environment]::SetEnvironmentVariable("Path", $env:PATH + ";$env:USERPROFILE\.local\bin", "User")

``` pwsh sessions
C:\Users\lociu\code> goose

goose-configure

Opening browser for authentication...
Auth URL: https://openrouter.ai/auth? XXX
Waiting for authentication callback...
Authorization code received. Exchanging for API key...
Received code: 5XX
Exchanging code for API key...
Code: 5XX
Code verifier length: 128
Code challenge: nDXX

Authentication complete!

Configuring OpenRouter...
✓ OpenRouter configuration complete
✓ Models configured successfully

Testing configuration...
⚠️  Configuration test failed: Credits exhausted: This request requires more credits, or fewer max_tokens. You requested up to 64000 tokens, but can only afford 2666. To increase, visit https://openrouter.ai/settings/credits and upgrade to a paid account
Your settings have been saved, but there may be an issue with the connection.
```
```pwsh session
C:\Users\lociu\code> goose

    __( O)>  ● new session · openrouter anthropic/claude-sonnet-4
   \____)    20260917_1 · C:\Users\lociu\code
     L L     goose is ready
  ⏳ loading extensions in background...
  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ 0% 0/1.0M
```

goose session --with-streamable-http-extension "http://127.0.0.1:4201/mcp" --with-streamable-http-extension "http://127.0.0.1:4202/mcp"

goose 
/mode approve
/model openrouter/free



##
``` pwsh session
## Available MCP Extensions & Resources

### Currently Enabled Extensions:
| Extension              | Description                                        |
|------------------------|----------------------------------------------------|
| **127_0_0_1_4201_mcp** | Microscope control (stage movement, image capture) |
| **127_0_0_1_4202_mcp** | FTP file operations (download, upload, list)       |
| **analyze**            | Code structure analysis via tree-sitter            |
| **apps**               | Custom HTML/CSS/JavaScript app creation            |
| **developer**          | Terminal & file operations                         |
| **extensionmanager**   | Extension management                               |
| **skills**             | Skill loading system                               |
| **summon**             | Agent delegation                                   |
| **todo**               | Task tracking                                      |
| **tom**                | (unknown)                                          |
### Available Resources:
| Extension              | Resource     | URI                         |
|------------------------|--------------|-----------------------------|
| **apps**               | clock        | `ui://apps/clock`           |
| **127_0_0_1_4201_mcp** | latest_image | `microscope://latest_image` |
### Additional Extensions Available to Enable:
- **chatrecall** - Search past conversations and load session summaries
- **summarize** - Load files/directories and get LLM summaries
- **code_execution** - Execute code through extension calls

```
"""Serviços compartilhados entre módulos, acessados por ctx.servico("nome"):

- "uex"   uex_api.ClienteUEX    preços, terminais, naves, refino (UEX Corp)
- "wiki"  wiki_api.ClienteWiki  estatísticas das naves (Star Citizen Wiki)
- "cache" api_cache.CacheAPI    cache das respostas no SQLite

ocr/ é usado diretamente pelo scanner da Mineração (um motor por thread).
"""

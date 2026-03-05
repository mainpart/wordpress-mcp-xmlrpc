# wp-xmlrpc-mcp

MCP-сервер для управления WordPress через XML-RPC API. Оборачивает методы `wp.*` и отдаёт результаты в компактном JSON.

## Требования

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (зависимости устанавливаются автоматически при первом запуске)

## Настройка в Claude Code

Добавьте сервер в `.claude/settings.json` (или `~/.claude.json` для глобальной конфигурации):

```json
{
  "mcpServers": {
    "wordpress-xmlrpc": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mainpart/wordpress-mcp-xmlrpc", "wordpress-mcp-xmlrpc"],
      "env": {
        "WP_URL": "https://your-site.example.com",
        "WP_USERNAME": "your-username",
        "WP_PASSWORD": "your-application-password"
      }
    }
  }
}
```

`WP_PASSWORD` — рекомендуется использовать Application Password (Пользователи -> Профиль -> Пароли приложений).

## Фильтрация полей ответа

Для экономии токенов сервер удаляет из ответов ненужные поля. Списки удаляемых полей настраиваются через переменные окружения (через запятую). Если переменная не задана, используются значения по умолчанию.

| Переменная | По умолчанию |
|---|---|
| `WP_DROP_POST_FIELDS` | `guid,link,ping_status,comment_status,sticky,format,template,class_list,meta,text_more,wp_page_template,wp_password,permaLink,page_status,post_date_gmt,post_modified,post_modified_gmt,post_status,post_type,post_name,post_password,post_excerpt,post_parent,post_mime_type,menu_order,post_thumbnail,post_format,terms,custom_fields` |
| `WP_DROP_COMMENT_FIELDS` | `author_ip,author_url,link,type,post_title,status,author_email,user_id,post_id,parent` |
| `WP_DROP_MEDIA_FIELDS` | `link,parent,guid,comment_status,ping_status,sticky,format,template,meta,terms` |
| `WP_DROP_USER_FIELDS` | `url` |

Чтобы отключить фильтрацию для категории, задайте пустую строку: `"WP_DROP_POST_FIELDS": ""`.

Пример — оставить только `link` в фильтре постов:

```json
{
  "env": {
    "WP_URL": "...",
    "WP_USERNAME": "...",
    "WP_PASSWORD": "...",
    "WP_DROP_POST_FIELDS": "link"
  }
}
```

## Управление видимостью инструментов

Переменная `MCP_ENABLED_TOOLS` задаёт список доступных инструментов (через запятую). По умолчанию:

```
getPosts,getPost,getComments,getComment,getCommentCount,getMediaLibrary,getMediaItem
```

Чтобы изменить набор, перечислите нужные имена в `env`:

```json
{
  "env": {
    "MCP_ENABLED_TOOLS": "getPosts,getPost,getComments,getComment,newComment,editComment"
  }
}
```

### Все доступные инструменты

**Чтение — записи, комментарии, медиа:**
- `getPosts`, `getPost` — список и детали записей
- `getComments`, `getComment`, `getCommentCount` — комментарии
- `getMediaLibrary`, `getMediaItem` — медиатека

**Чтение — страницы, таксономии, пользователи, опции:**
- `getPages`, `getPage`, `getPageList`, `getPageStatusList`, `getPageTemplates`
- `getPostFormats`, `getPostStatusList`, `getPostType`, `getPostTypes`
- `getAuthors`, `getUsers`, `getUser`, `getProfile`
- `getCategories`, `getTags`, `getTaxonomies`, `getTaxonomy`, `getTerms`, `getTerm`
- `getOptions`, `getRevisions`, `getCommentStatusList`

**Создание и редактирование:**
- `newPost`, `editPost`, `newPage`, `editPage`
- `newComment`, `editComment`
- `newCategory`, `newTerm`, `editTerm`
- `editProfile`, `setOptions`, `uploadFile`
- `suggestCategories`, `restoreRevision`

**Удаление:**
- `deletePost`, `deletePage`, `deleteComment`
- `deleteCategory`, `deleteTerm`, `deleteFile`

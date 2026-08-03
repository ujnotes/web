# Ujnotes - web

## Technology:
- Nginx - aggregator reverse proxy, docker based
- Supports HTTPS with a self-signed certificate
- Routes to components Ujnotes : [`web-site`](https://github.com/ujnotes/web-site) - docker based

## Localhost - hosts file

- ujnotes.local - 127.0.0.1

## Project stcuture

```
Web
│
├── Site
│   └── Project             (ujnotes/web-site)
|       ├── root\framework  (blank-org/cutie - submoduled)
│       ├── interim
│       └── public
│
├── Project                 (ujnotes/web * this repo)
│   ├── interim             (ujnotes/web-interim)
│   └── public              (ujnotes/web-public > ujnotes.com)
|
│
└── Tiggu                   (blank-org/tiggu)
│
└── Firebase                (blank-org/firebase)
```

## Certificate

For SSL generate `server.key` & `server.crt` files

cert_details.txt :

```
[req]
distinguished_name = req_distinguished_name
prompt = no

[req_distinguished_name]
CN = ujnotes.local
```

Generate self-signed certificate
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout server.key -out server.crt -config cert_details.txt
```

You may also want to add this to your trusted-root CA store  
\- so that you are not presented with the *insecure origin* message when navigating to `ujnotes.local`


## Manage
`Firebase` : docker based - project is to provide firebase CLI.  
Used to setup CI; Not required afterwards - hence separate.

## Website
`ujnotes.com` \> mapped to `public` directory

## Multilanguage URLs

English is the default language and is served directly at the base URL. For
example, `/world/philosophy/hindu` renders English and does not redirect to an
`/en/...` URL. Native translations use a language prefix, such as
`/hi/world/philosophy/hindu`.

When a requested translation is unavailable, Cutie falls back to the English
component without redirecting away from the language-prefixed URL. Canonical
and `hreflang` metadata use the unprefixed English URL as `x-default`.

## Setup
- Run following script to setup the directory structure & repos
```bash
base_directory="web"

# function to create directory and clone git repository
clone_repo() {
    local path=$1
    local remote_url=$2
    local full_path="$base_directory/$path"

    # create base directory if it doesn't exist
    mkdir -p "$base_directory"
    
    # clone the repository into the specified path
    git clone --recurse-submodules "$remote_url" "$full_path"
}

# clone git repositories into specific paths
clone_repo "site/project" "https://github.com/ujnotes/web-site.git"
clone_repo "project" "https://github.com/ujnotes/web.git"
clone_repo "project/interim" "https://github.com/ujnotes/web-interim.git"
clone_repo "project/public" "https://github.com/ujnotes/web-public.git"
clone_repo "tiggu" "https://github.com/blank-org/tiggu.git"
# clone_repo "firebase" "https://github.com/blank-org/firebase.git"
```

- Then build and run docker for `web/project`

## Notion publication workflow

`.github/workflows/publish-notion.yml` polls the production Notion database every
15 minutes and can also be started manually. A scheduled run is a successful no-op
when there are no queued pages. It refuses to choose between multiple
`Status=publish` pages; use the manual `slug` input to select one explicitly.

Manual runs default to `dry_run=true`. A dry run fetches through NCMS, renders the
article with Cutie/Tiggu, validates the generated files, and uploads an artifact.
It does not push either website repository or change Notion.

The `prod` GitHub environment must define:

- Variable `NOTION_DATABASE_ID`
- Repository or environment secret `NOTION_API_KEY`
- Repository or environment secret `UJNOTES_PUBLISH_TOKEN`

The publish token needs read access to `ujnotes/web`, `ujnotes/web-site`, and
`ujnotes/web-public`. It needs Contents write access to `ujnotes/web-site` and
`ujnotes/web-public`. NCMS and Tiggu are checked out without the token.

The guarded lifecycle is:

1. NCMS renders exactly one page into an isolated bundle with git and Notion
   mutations disabled.
2. The workflow merges that article into `web-site`, builds it, and validates the
   generated HTML, JSON, optional cover, Firebase configuration, and sitemap.
3. Source and public artifacts are committed with explicit path allowlists.
4. The existing `web-public` push workflow deploys Firebase Hosting.
5. The workflow waits until the live JSON SHA-256 matches the generated file.
6. NCMS changes the Notion page from `publish` to `published`.

from python_graphql_client import GraphqlClient
import feedparser
import httpx
import json
import pathlib
import re
import os

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("PERSONAL_TOKEN", "")

def replace_chunk(content, marker, chunk):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    chunk = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(
        marker, chunk, marker)
    return r.sub(chunk, content)


def make_query(after_cursor=None):
    return """
query {
  viewer {
    repositories(first: 100, privacy: PUBLIC, after:AFTER) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        releases(last:1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
""".replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    )


commits_query = """
query {
  viewer {
    repositories(first: 100, privacy: PUBLIC) {
      nodes {
        name
        url
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 1, author: {emails: ["constantin@metzworld.com"]}) {
                nodes {
                  ... on Commit {
                    url
                    committedDate
                    author {
                      name
                      email
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


def fetch_releases(oauth_token):
    repos = []
    releases = []
    repo_names = set()
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
        print()
        print(json.dumps(data, indent=4))
        print()
        for repo in data["data"]["viewer"]["repositories"]["nodes"]:
            if repo["releases"]["totalCount"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                releases.append(
                    {
                        "repo": repo["name"],
                        "release": repo["releases"]["nodes"][0]["name"]
                        .replace(repo["name"], "")
                        .strip(),
                        "published_at": repo["releases"]["nodes"][0][
                            "publishedAt"
                        ].split("T")[0],
                        "url": repo["releases"]["nodes"][0]["url"],
                    }
                )
        has_next_page = data["data"]["viewer"]["repositories"]["pageInfo"][
            "hasNextPage"
        ]
        after_cursor = data["data"]["viewer"]["repositories"]["pageInfo"]["endCursor"]
    return releases


def fetch_commits(oauth_token):
    repos = []
    commits = []
    repo_names = set()

    data = client.execute(
            query=commits_query,
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )

    print()
    print(json.dumps(data, indent=4))
    print()
    for repo in data["data"]["viewer"]["repositories"]["nodes"]:
        if len(repo["defaultBranchRef"]["target"]["history"]["nodes"]) == 1 and repo["name"] not in repo_names:
            repos.append(repo)
            repo_names.add(repo["name"])
            commits.append(
                {
                    "repo": repo["name"],
                    "repo_url": repo["url"],
                    "url": repo["defaultBranchRef"]["target"]["history"]["nodes"][0]["url"],
                    "date": repo["defaultBranchRef"]["target"]["history"]["nodes"][0]["commited_date"],
                    "oid": repo["defaultBranchRef"]["target"]["history"]["nodes"][0]["oid"][:7],
                }
            )


    return commits

if __name__ == "__main__":
    readme = root / "README.md"
    releases = fetch_releases(TOKEN)
    releases.sort(key=lambda r: r["published_at"], reverse=True)
    md="\n".join(
        [
            "* [{repo} {release}]({url}) - {published_at}".format(**release)
            for release in releases[:5]
        ]
    )
    readme_contents=readme.open().read()
    rewritten=replace_chunk(readme_contents, "recent_releases", md)

    commits=fetch_commits(TOKEN)
    commits.sort(key = lambda r: r["date"], reverse=True)
    md = "\n".join(
        [
            "* [{repo}]({repo_url}) #[{oid}]({url}) - {date}".format(**commit)
            for commit in commits[:5]
        ]
    )
    readme_contents=readme.open().read()
    rewritten=replace_chunk(readme_contents, "recent_commits", md)

    readme.open("w").write(rewritten)

from python_graphql_client import GraphqlClient
from datetime import datetime
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

    if marker == 'recent_releases':
      chunk = """
| Repository | Version | Date |
| :- | :- | :- |
""" + chunk
    elif marker == 'recent_commits':
      chunk = """
| Repository | Commit | Date |
| :- | :- | :- |      
""" + chunk

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
        url
        releases(last:1) {
          totalCount
          nodes {
            name
            publishedAt
            url
            tag {
              name
            }
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
  search(query: "Keimeno", type: USER, last: 1) {
    nodes {
      ... on User {
       	contributionsCollection {
          commitContributionsByRepository {
            repository {
              isPrivate
              name
              url
              refs(refPrefix: "refs/heads/", first: 30) {
                edges {
                  node {
                  	target {
                      ... on Commit {
                        history(first: 1, author: {emails: ["constantin@metzworld.com", "58604248+Keimeno@users.noreply.github.com"]}) {
                          nodes {
                            ... on Commit {
                              url
                              abbreviatedOid
                              committedDate
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

        for repo in data["data"]["viewer"]["repositories"]["nodes"]:
            if repo["releases"]["totalCount"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                releases.append(
                    {
                        "repo": repo["name"],
                        "repo_url": repo["url"],
                        "release": repo["releases"]["nodes"][0]["name"]
                        .replace(repo["name"], "")
                        .strip(),
                        "published_at": repo["releases"]["nodes"][0][
                            "publishedAt"
                        ].split("T")[0],
                        "tag_name": repo["releases"]["nodes"][0]["tag"]["name"],
                        "tag_url": repo["releases"]["nodes"][0]["url"],
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

    for repo in data["data"]["search"]["nodes"][0]["contributionsCollection"]["commitContributionsByRepository"]:
        name = repo.get("name")

        if not name:
            print("Continued")
            continue
        elif repo["name"] not in repo_names:
            print("doing run")
            repos.append(repo)
            repo_names.add(repo["name"])
            if repo["isPrivate"] == True:
              print("it is private!")
              continue

            for branch in repo["refs"]["edges"]:
              nodeList = branch["node"]["target"]["history"]["nodes"]
              if len(nodeList) == 0:
                continue

              commit = nodeList[0]
              commits.append(
                  {
                      "repo": repo["name"],
                      "repo_url": repo["url"],
                      "url": commit["url"],
                      "date": commit["committedDate"].split("T")[0],
                      "oid": commit["abbreviatedOid"],
                  }
              )


    return commits

if __name__ == "__main__":
    readme = root / "README.md"
    releases = fetch_releases(TOKEN)
    releases.sort(key=lambda r: r["published_at"], reverse=True)
    md="\n".join(
        [
            "| [{repo}]({repo_url}) | [{tag_name}]({tag_url}) | {published_at} |".format(**release)
            for release in releases[:5]
        ]
    )
    readme_contents=readme.open().read()
    rewritten=replace_chunk(readme_contents, "recent_releases", md)

    commits=fetch_commits(TOKEN)
    commits.sort(key = lambda r: r["date"], reverse=True)
    md = "\n".join(
        [
            "| [{repo}]({repo_url}) | [{oid}]({url}) | {date} |".format(**commit)
            for commit in commits[:5]
        ]
    )
    rewritten=replace_chunk(rewritten, "recent_commits", md)

    now = datetime.now()
    md = now.strftime("%Y-%m-%d %H:%M")
    rewritten=replace_chunk(rewritten, "last_updated", md)

    readme.open("w").write(rewritten)

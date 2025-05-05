import json
import logging
from typing import List, Optional, Dict, Any
from agno.tools import tool
from github import GithubException, UnknownObjectException, PaginatedList
from integrations.github_client import get_github_client
from datetime import datetime

log = logging.getLogger(__name__)


"""
NOTE: This is 100% generated code.
"""


def _handle_github_exception(e: GithubException, context: str) -> str:
    """Formats GitHub exceptions into a standard error JSON string."""
    status = getattr(e, "status", "N/A")
    # Attempt to parse data if it's a string representation of a dict
    error_data = getattr(e, "data", {})
    details_message = str(e)  # Default message
    if isinstance(error_data, str):
        try:
            error_data = json.loads(error_data)
        except json.JSONDecodeError:
            pass  # Keep original string if not JSON

    if isinstance(error_data, dict):
        details_message = error_data.get("message", str(e))
        # Include errors list if present
        if "errors" in error_data:
            details_message += f" Errors: {json.dumps(error_data['errors'])}"

    log.error(
        f"GitHub API error in {context}: Status {status}, Message: {details_message}",
        exc_info=True,
    )
    return json.dumps(
        {
            "error": f"GitHub API Error ({context})",
            "status_code": status,
            "details": details_message,
        }
    )


def _handle_general_exception(e: Exception, context: str) -> str:
    """Formats general exceptions into a standard error JSON string."""
    log.error(f"Unexpected error in {context}: {e}", exc_info=True)
    # Ensure the details are serializable
    details = str(e)
    try:
        json.dumps(details)
    except TypeError:
        details = repr(e)  # Fallback for non-serializable exceptions
    return json.dumps({"error": f"Tool Error ({context})", "details": details})


def _process_paginated_list(
    paginated_list: PaginatedList.PaginatedList, page: int, per_page: int
) -> List[Any]:
    """Helper to get a specific page from a PyGithub PaginatedList."""
    try:
        # PaginatedList is 0-indexed for pages
        page_index = page - 1
        if page_index < 0:
            log.warning(f"Requested page {page}, using page 1 (index 0).")
            page_index = 0
        # Fetch the specific page - PyGithub applies per_page implicitly here based on original call,
        # but get_page() itself doesn't take per_page. Let's fetch and slice.
        items = paginated_list.get_page(page_index)
        # Manually slice to respect per_page, as get_page might return full page size.
        # Note: This is inefficient if per_page is small, but necessary for correctness.
        start_index = 0  # Slicing a page always starts at 0 for that page
        end_index = per_page
        if end_index > len(items):
            end_index = len(items)
        log.debug(
            f"Fetched page index {page_index}, slicing items {start_index}:{end_index} (requested per_page={per_page})"
        )
        return items[start_index:end_index]
    except IndexError:
        log.info(f"Page index {page_index} (requested page {page}) is out of bounds.")
        return []  # Return empty list if page doesn't exist
    except Exception as e:
        log.warning(f"Error processing paginated list page {page}: {e}")
        return []


# === Tool Definitions ===


@tool
def list_commits(
    owner: str, repo: str, sha: Optional[str] = None, page: int = 1, per_page: int = 30
) -> str:
    """
    Gets a list of commits for a specific repository branch or SHA.

    Args:
        owner (str): The owner of the repository (username or organization). REQUIRED.
        repo (str): The name of the repository. REQUIRED.
        sha (Optional[str]): The SHA or branch name to list commits from. If None, uses the default branch. OPTIONAL. Default: None.
        page (int): Page number for pagination (starts at 1). Default: 1.
        per_page (int): Number of commits per page (max 100). Default: 30.

    Returns:
        str: A JSON string representation of a list of commit objects. Each object contains simplified commit details like sha, message, author login, and date.
             Returns '[]' if no commits are found. Returns error JSON on failure.
    """
    context = f"list_commits({owner}/{repo}, sha={sha}, page={page}, per_page={per_page})"  # Added per_page
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        repo_obj = gh.get_repo(f"{owner}/{repo}")
        log.debug(
            f"Fetching commits for {owner}/{repo}"
            + (f" from ref '{sha}'" if sha else " from default branch")
        )
        # Pass per_page to the initial call if supported, otherwise rely on _process_paginated_list slicing
        commits_paginated = repo_obj.get_commits(
            sha=sha
        )  # Let's assume get_commits doesn't take per_page directly based on common patterns
        commits_page = _process_paginated_list(commits_paginated, page, per_page)

        commit_list = []
        for commit in commits_page:
            author_login = commit.author.login if commit.author else None
            # Use committer date as it usually reflects when commit was added to the branch
            commit_date_obj = (
                commit.commit.committer.date if commit.commit.committer else None
            )
            commit_date = commit_date_obj.isoformat() if commit_date_obj else None

            commit_list.append(
                {
                    "sha": commit.sha,
                    "message": commit.commit.message,
                    "author_login": author_login,
                    "date": commit_date,
                }
            )
        log.info(
            f"Found {len(commit_list)} commits for {context} (Page {page}, PerPage {per_page})"
        )
        return json.dumps(commit_list)

    except UnknownObjectException:
        log.warning(f"Repository or ref not found for {context}")
        return json.dumps(
            {
                "error": "Repository or reference (branch/sha) not found",
                "status_code": 404,
            }
        )
    except GithubException as e:
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def get_pull_request(owner: str, repo: str, pull_number: int) -> str:
    """
    Gets detailed information for a specific pull request.

    Args:
        owner (str): The owner of the repository. REQUIRED.
        repo (str): The name of the repository. REQUIRED.
        pull_number (int): The number of the pull request. REQUIRED.

    Returns:
        str: A JSON string representation of the pull request details. Returns error JSON on failure.
             Uses the `.raw_data` attribute for comprehensive details.
    """
    context = f"get_pull_request({owner}/{repo}#{pull_number})"
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        repo_obj = gh.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pull_number)
        log.info(f"Successfully fetched details for {context}")
        # Using raw_data for simplicity, includes all fields.
        # Manually convert datetime objects to ISO strings for JSON serialization
        raw_data = pr.raw_data
        for key, value in raw_data.items():
            if isinstance(value, datetime):
                raw_data[key] = value.isoformat()
            elif isinstance(
                value, dict
            ):  # Handle nested dicts like 'user', 'head', 'base'
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, datetime):
                        value[sub_key] = sub_value.isoformat()
        return json.dumps(raw_data)

    except UnknownObjectException:
        log.warning(f"Pull request not found for {context}")
        return json.dumps({"error": "Pull request not found", "status_code": 404})
    except GithubException as e:
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def get_pull_request_status(owner: str, repo: str, pull_number: int) -> str:
    """
    Gets the combined status (checks) for the head commit of a pull request.

    Args:
        owner (str): The owner of the repository. REQUIRED.
        repo (str): The name of the repository. REQUIRED.
        pull_number (int): The number of the pull request. REQUIRED.

    Returns:
        str: A JSON string representation of the combined status, including overall state and individual statuses.
             Returns error JSON on failure.
    """
    context = f"get_pull_request_status({owner}/{repo}#{pull_number})"
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        repo_obj = gh.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pull_number)
        head_sha = pr.head.sha
        if not head_sha:
            return json.dumps(
                {"error": f"Could not determine head SHA for PR {pull_number}"}
            )

        log.debug(f"Fetching combined status for commit {head_sha} ({context})")
        # Important: Get the Commit object first, then its combined status
        commit_obj = repo_obj.get_commit(head_sha)
        combined_status = commit_obj.get_combined_status()

        status_list = []
        for status in combined_status.statuses:
            status_list.append(
                {
                    "context": status.context,
                    "state": status.state,
                    "description": status.description,
                    "target_url": status.target_url,
                    "avatar_url": status.avatar_url,
                    # Ensure datetime objects are converted to ISO strings
                    "created_at": status.created_at.isoformat()
                    if isinstance(status.created_at, datetime)
                    else None,
                    "updated_at": status.updated_at.isoformat()
                    if isinstance(status.updated_at, datetime)
                    else None,
                }
            )

        result = {
            "state": combined_status.state,
            "sha": combined_status.sha,
            "total_count": combined_status.total_count,
            "statuses": status_list,
        }
        log.info(
            f"Successfully fetched combined status for {context}: State '{result['state']}'"
        )
        return json.dumps(result)

    except UnknownObjectException:
        log.warning(f"Pull request or commit not found for {context}")
        return json.dumps(
            {"error": "Pull request or head commit not found", "status_code": 404}
        )
    except GithubException as e:
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def get_pull_request_reviews(
    owner: str, repo: str, pull_number: int, page: int = 1, per_page: int = 30
) -> str:
    """
    Gets reviews for a specific pull request.

    Args:
        owner (str): The owner of the repository. REQUIRED.
        repo (str): The name of the repository. REQUIRED.
        pull_number (int): The number of the pull request. REQUIRED.
        page (int): Page number for pagination (starts at 1). Default: 1.
        per_page (int): Number of reviews per page (max 100). Default: 30.

    Returns:
        str: A JSON string representation of a list of review objects. Each object contains details like reviewer, state, body, and submission time.
             Returns '[]' if no reviews found. Returns error JSON on failure.
    """
    context = f"get_pull_request_reviews({owner}/{repo}#{pull_number}, page={page}, per_page={per_page})"  # Added per_page
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        repo_obj = gh.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pull_number)
        reviews_paginated = pr.get_reviews()
        reviews_page = _process_paginated_list(reviews_paginated, page, per_page)

        review_list = []
        for review in reviews_page:
            # Ensure datetime objects are converted to ISO strings
            submitted_at_iso = (
                review.submitted_at.isoformat()
                if isinstance(review.submitted_at, datetime)
                else None
            )
            review_list.append(
                {
                    "id": review.id,
                    "user_login": review.user.login if review.user else None,
                    "body": review.body,
                    "state": review.state,
                    "html_url": review.html_url,
                    "submitted_at": submitted_at_iso,
                }
            )
        log.info(
            f"Found {len(review_list)} reviews for {context} (Page {page}, PerPage {per_page})"
        )
        return json.dumps(review_list)

    except UnknownObjectException:
        log.warning(f"Pull request not found for {context}")
        return json.dumps({"error": "Pull request not found", "status_code": 404})
    except GithubException as e:
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def get_pull_request_files(
    owner: str, repo: str, pull_number: int, page: int = 1, per_page: int = 30
) -> str:
    """
    Gets the list of files changed in a specific pull request.

    Args:
        owner (str): The owner of the repository. REQUIRED.
        repo (str): The name of the repository. REQUIRED.
        pull_number (int): The number of the pull request. REQUIRED.
        page (int): Page number for pagination (starts at 1). Default: 1.
        per_page (int): Number of files per page (max 100). Default: 30.

    Returns:
        str: A JSON string representation of a list of file change objects. Each object contains details like filename, status, additions, deletions.
             Returns '[]' if no files changed or PR not found. Returns error JSON on failure.
    """
    context = f"get_pull_request_files({owner}/{repo}#{pull_number}, page={page}, per_page={per_page})"  # Added per_page
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        repo_obj = gh.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pull_number)
        files_paginated = pr.get_files()
        files_page = _process_paginated_list(files_paginated, page, per_page)

        file_list = []
        for file in files_page:
            file_list.append(
                {
                    "sha": file.sha,
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "blob_url": file.blob_url,
                    "raw_url": file.raw_url,
                    "contents_url": file.contents_url,
                    "patch": file.patch,  # Can be large, consider omitting if not needed
                }
            )
        log.info(
            f"Found {len(file_list)} changed files for {context} (Page {page}, PerPage {per_page})"
        )
        return json.dumps(file_list)

    except UnknownObjectException:
        log.warning(f"Pull request not found for {context}")
        return json.dumps({"error": "Pull request not found", "status_code": 404})
    except GithubException as e:
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def search_issues(
    query: str,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
) -> str:
    """
    Searches for issues and pull requests across GitHub using GitHub's search syntax.

    Args:
        query (str): The search query string (e.g., 'repo:owner/repo is:open is:pr label:bug'). REQUIRED. See GitHub search documentation for syntax.
        sort (Optional[str]): What to sort results by. Can be 'comments', 'reactions', 'reactions-+1', 'reactions--1', 'reactions-smile', 'reactions-thinking_face', 'reactions-heart', 'reactions-tada', 'interactions', 'created', 'updated'. Default: 'best match'. OPTIONAL.
        order (Optional[str]): The direction to sort by. Can be 'asc' or 'desc'. Default: 'desc'. OPTIONAL.
        page (int): Page number for pagination (starts at 1). Default: 1.
        per_page (int): Number of items per page (max 100). Default: 30.

    Returns:
        str: A JSON string representation of the search results, including a list of simplified issue/PR objects and the total count.
             Returns error JSON on failure.
    """
    context = f"search_issues(query='{query[:50]}...', page={page}, per_page={per_page})"  # Added per_page
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        # Build kwargs dynamically to avoid passing None to PyGithub's assert
        search_kwargs: Dict[str, Any] = {"query": query}
        if sort is not None:
            search_kwargs["sort"] = sort
        if order is not None:
            search_kwargs["order"] = order

        log.debug(f"Calling gh.search_issues with kwargs: {search_kwargs}")
        results_paginated = gh.search_issues(**search_kwargs)  # Use **kwargs
        results_page = _process_paginated_list(results_paginated, page, per_page)

        issue_list = []
        for item in results_page:
            repo_name = item.repository.full_name if item.repository else None
            assignee_login = item.assignee.login if item.assignee else None
            pr_details = item.pull_request  # This is metadata, not full PR details
            # Ensure datetime objects are converted to ISO strings
            created_at_iso = (
                item.created_at.isoformat()
                if isinstance(item.created_at, datetime)
                else None
            )
            updated_at_iso = (
                item.updated_at.isoformat()
                if isinstance(item.updated_at, datetime)
                else None
            )

            issue_list.append(
                {
                    "number": item.number,
                    "title": item.title,
                    "state": item.state,
                    "repository": repo_name,
                    "is_pull_request": pr_details is not None,
                    "author_login": item.user.login if item.user else None,
                    "assignee_login": assignee_login,
                    "created_at": created_at_iso,
                    "updated_at": updated_at_iso,
                    "html_url": item.html_url,
                    "comments_count": item.comments,
                }
            )

        total_count = results_paginated.totalCount
        log.info(
            f"Search found {total_count} total issues/PRs. Returning {len(issue_list)} for page {page}, per_page {per_page}."
        )
        return json.dumps({"total_count": total_count, "items": issue_list})

    except GithubException as e:
        # GitHub search API often returns 422 for invalid queries
        if e.status == 422:
            log.warning(
                f"Invalid GitHub search query: {query}. Error: {e.data.get('message')}"
            )
            return json.dumps(
                {
                    "error": "Invalid search query syntax",
                    "status_code": 422,
                    "details": e.data.get("message"),
                }
            )
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def list_branches(owner: str, repo: str, page: int = 1, per_page: int = 30) -> str:
    """
    Lists branches for a specific repository.

    Args:
        owner (str): The owner of the repository. REQUIRED.
        repo (str): The name of the repository. REQUIRED.
        page (int): Page number for pagination (starts at 1). Default: 1.
        per_page (int): Number of branches per page (max 100). Default: 30.

    Returns:
        str: A JSON string representation of a list of branch objects, including name and commit SHA.
             Returns '[]' if no branches found. Returns error JSON on failure.
    """
    context = f"list_branches({owner}/{repo}, page={page}, per_page={per_page})"  # Added per_page
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        repo_obj = gh.get_repo(f"{owner}/{repo}")
        branches_paginated = repo_obj.get_branches()
        branches_page = _process_paginated_list(branches_paginated, page, per_page)

        branch_list = []
        for branch in branches_page:
            branch_list.append(
                {
                    "name": branch.name,
                    "commit_sha": branch.commit.sha if branch.commit else None,
                    "protected": branch.protected,
                }
            )
        log.info(
            f"Found {len(branch_list)} branches for {context} (Page {page}, PerPage {per_page})"
        )
        return json.dumps(branch_list)

    except UnknownObjectException:
        log.warning(f"Repository not found for {context}")
        return json.dumps({"error": "Repository not found", "status_code": 404})
    except GithubException as e:
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)


@tool
def search_repositories(
    query: str,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
) -> str:
    """
    Searches for repositories across GitHub.

    Args:
        query (str): The search query string (e.g., 'language:python stars:>1000'). REQUIRED. See GitHub search documentation.
        sort (Optional[str]): What to sort results by. Can be 'stars', 'forks', 'help-wanted-issues', 'updated'. Default: 'best match'. OPTIONAL.
        order (Optional[str]): The direction to sort by. Can be 'asc' or 'desc'. Default: 'desc'. OPTIONAL.
        page (int): Page number for pagination (starts at 1). Default: 1.
        per_page (int): Number of items per page (max 100). Default: 30.

    Returns:
        str: A JSON string representation of the search results, including a list of simplified repository objects and the total count.
             Returns error JSON on failure.
    """
    context = f"search_repositories(query='{query[:50]}...', page={page}, per_page={per_page})"  # Added per_page
    log.info(f"Tool call: {context}")
    gh = get_github_client()
    if not gh:
        return json.dumps({"error": "GitHub client initialization failed."})

    try:
        # Build kwargs dynamically to avoid PyGithub assertion error on None sort
        search_kwargs: Dict[str, Any] = {"query": query}
        if sort is not None:
            # Validate sort here before passing to library to avoid assertion
            allowed_sorts = ["stars", "forks", "help-wanted-issues", "updated"]
            if sort not in allowed_sorts:
                log.warning(
                    f"Invalid sort parameter '{sort}' provided. Using default 'best match'. Allowed: {allowed_sorts}"
                )
                # Don't pass invalid sort to the library
            else:
                search_kwargs["sort"] = sort
        if order is not None:
            search_kwargs["order"] = order

        log.debug(f"Calling gh.search_repositories with kwargs: {search_kwargs}")
        results_paginated = gh.search_repositories(**search_kwargs)  # Use **kwargs
        results_page = _process_paginated_list(results_paginated, page, per_page)

        repo_list = []
        for repo in results_page:
            # Ensure datetime objects are converted to ISO strings
            updated_at_iso = (
                repo.updated_at.isoformat()
                if isinstance(repo.updated_at, datetime)
                else None
            )
            repo_list.append(
                {
                    "full_name": repo.full_name,
                    "owner_login": repo.owner.login if repo.owner else None,
                    "name": repo.name,  # Added name for consistency
                    "description": repo.description,
                    "stars": repo.stargazers_count,
                    "forks": repo.forks_count,
                    "language": repo.language,
                    "updated_at": updated_at_iso,
                    "html_url": repo.html_url,
                    "private": repo.private,
                    "default_branch": repo.default_branch,  # Added default_branch
                    "visibility": "private"
                    if repo.private
                    else "public",  # Added visibility
                }
            )

        total_count = results_paginated.totalCount
        log.info(
            f"Search found {total_count} total repositories. Returning {len(repo_list)} for page {page}, per_page {per_page}."
        )
        return json.dumps({"total_count": total_count, "items": repo_list})

    except GithubException as e:
        if e.status == 422:  # Unprocessable Entity (often invalid query)
            log.warning(
                f"Invalid GitHub search query: {query}. Error: {e.data.get('message')}"
            )
            return json.dumps(
                {
                    "error": "Invalid search query syntax",
                    "status_code": 422,
                    "details": e.data.get("message"),
                }
            )
        return _handle_github_exception(e, context)
    except Exception as e:
        return _handle_general_exception(e, context)

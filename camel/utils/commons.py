# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
import importlib
import os
import platform
import re
import socket
import subprocess
import time
import zipfile
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    cast,
)
from urllib.parse import urlparse

import pydantic
import requests
from pydantic import BaseModel

from camel.types import TaskType

from .constants import Constants

F = TypeVar('F', bound=Callable[..., Any])


def print_text_animated(text, delay: float = 0.02, end: str = ""):
    r"""Prints the given text with an animated effect.

    Args:
        text (str): The text to print.
        delay (float, optional): The delay between each character printed.
            (default: :obj:`0.02`)
        end (str, optional): The end character to print after each
            character of text. (default: :obj:`""`)
    """
    for char in text:
        print(char, end=end, flush=True)
        time.sleep(delay)


def get_prompt_template_key_words(template: str) -> Set[str]:
    r"""Given a string template containing curly braces {}, return a set of
    the words inside the braces.

    Args:
        template (str): A string containing curly braces.

    Returns:
        List[str]: A list of the words inside the curly braces.

    Example:
        >>> get_prompt_template_key_words('Hi, {name}! How are you {status}?')
        {'name', 'status'}
    """
    return set(re.findall(r'{([^}]*)}', template))


def get_first_int(string: str) -> Optional[int]:
    r"""Returns the first integer number found in the given string.

    If no integer number is found, returns None.

    Args:
        string (str): The input string.

    Returns:
        int or None: The first integer number found in the string, or None if
            no integer number is found.
    """
    match = re.search(r'\d+', string)
    if match:
        return int(match.group())
    else:
        return None


def download_tasks(task: TaskType, folder_path: str) -> None:
    r"""Downloads task-related files from a specified URL and extracts them.

    This function downloads a zip file containing tasks based on the specified
    `task` type from a predefined URL, saves it to `folder_path`, and then
    extracts the contents of the zip file into the same folder. After
    extraction, the zip file is deleted.

    Args:
        task (TaskType): An enum representing the type of task to download.
        folder_path (str): The path of the folder where the zip file will be
                           downloaded and extracted.
    """
    # Define the path to save the zip file
    zip_file_path = os.path.join(folder_path, "tasks.zip")

    # Download the zip file from the Google Drive link
    response = requests.get(
        "https://huggingface.co/datasets/camel-ai/"
        f"metadata/resolve/main/{task.value}_tasks.zip"
    )

    # Save the zip file
    with open(zip_file_path, "wb") as f:
        f.write(response.content)

    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(folder_path)

    # Delete the zip file
    os.remove(zip_file_path)


def get_task_list(task_response: str) -> List[str]:
    r"""Parse the response of the Agent and return task list.

    Args:
        task_response (str): The string response of the Agent.

    Returns:
        List[str]: A list of the string tasks.
    """

    new_tasks_list = []
    task_string_list = task_response.strip().split('\n')
    # each task starts with #.
    for task_string in task_string_list:
        task_parts = task_string.strip().split(".", 1)
        if len(task_parts) == 2:
            task_id = ''.join(s for s in task_parts[0] if s.isnumeric())
            task_name = re.sub(r'[^\w\s_]+', '', task_parts[1]).strip()
            if task_name.strip() and task_id.isnumeric():
                new_tasks_list.append(task_name)
    return new_tasks_list


def check_server_running(server_url: str) -> bool:
    r"""Check whether the port refered by the URL to the server
    is open.

    Args:
        server_url (str): The URL to the server running LLM inference
            service.

    Returns:
        bool: Whether the port is open for packets (server is running).
    """
    parsed_url = urlparse(server_url)
    url_tuple = (parsed_url.hostname, parsed_url.port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(url_tuple)
    sock.close()

    # if the port is open, the result should be 0.
    return result == 0


def dependencies_required(*required_modules: str) -> Callable[[F], F]:
    r"""A decorator to ensure that specified Python modules
    are available before a function executes.

    Args:
        required_modules (str): The required modules to be checked for
            availability.

    Returns:
        Callable[[F], F]: The original function with the added check for
            required module dependencies.

    Raises:
        ImportError: If any of the required modules are not available.

    Example:
        ::

            @dependencies_required('numpy', 'pandas')
            def data_processing_function():
                # Function implementation...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            missing_modules = [
                m for m in required_modules if not is_module_available(m)
            ]
            if missing_modules:
                raise ImportError(
                    f"Missing required modules: {', '.join(missing_modules)}"
                )
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def is_module_available(module_name: str) -> bool:
    r"""Check if a module is available for import.

    Args:
        module_name (str): The name of the module to check for availability.

    Returns:
        bool: True if the module can be imported, False otherwise.
    """
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def api_keys_required(
    param_env_list: List[Tuple[Optional[str], str]],
) -> Callable[[F], F]:
    r"""A decorator to check if the required API keys are provided in the
    environment variables or as function arguments.

    Args:
        param_env_list (List[Tuple[Optional[str], str]]): A list of tuples
            where each tuple contains a function argument name (as the first
            element, or None) and the corresponding environment variable name
            (as the second element) that holds the API key.

    Returns:
        Callable[[F], F]: The original function wrapped with the added check
            for the required API keys.

    Raises:
        ValueError: If any of the required API keys are missing, either
            from the function arguments or environment variables.

    Example:
        ::

            @api_keys_required([
                ('api_key_arg', 'API_KEY_1'),
                ('another_key_arg', 'API_KEY_2'),
                (None, 'API_KEY_3'),
            ])
            def some_api_function(api_key_arg=None, another_key_arg=None):
                # Function implementation that requires API keys
    """
    import inspect

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            signature = inspect.signature(func)
            bound_arguments = signature.bind(*args, **kwargs)
            bound_arguments.apply_defaults()
            arguments = bound_arguments.arguments

            missing_keys = []
            for param_name, env_var_name in param_env_list:
                if not isinstance(env_var_name, str):
                    raise TypeError(
                        f"Environment variable name must be a string, got"
                        f" {type(env_var_name)}"
                    )

                value = None
                if (
                    param_name
                ):  # If param_name is provided, check function argument first
                    if not isinstance(param_name, str):
                        raise TypeError(
                            f"Parameter name must be a string, "
                            f"got {type(param_name)}"
                        )
                    value = arguments.get(param_name)
                    # If we found a valid value in arguments, continue to next
                    # item
                    if value:
                        continue

                # Check environment variable if no valid value found yet
                value = os.environ.get(env_var_name)
                if not value or value.strip() == "":
                    missing_keys.append(env_var_name)
                    
            key_way = "the official website"
            if env_var_name=='ANTHROPIC_API_KEY':
                key_way = "https://docs.anthropic.com/zh-CN/api/getting-started"
            elif env_var_name=='AIML_API_KEY':
                key_way = "https://aimlapi.com/"
            elif env_var_name=='COHERE_API_KEY':
                key_way = "https://cohere.com/"
            elif env_var_name=='DEEPSEEK_API_KEY':
                key_way = "https://www.deepseek.com/"
            elif env_var_name=='AZURE_OPENAI_API_KEY':
                key_way = "https://portal.azure.com/"
            elif env_var_name=='OPENAI_API_KEY':
                key_way = "https://platform.openai.com/docs/overview"
            elif env_var_name=='FISHAUDIO_API_KEY':
                key_way = "https://fish.audio/"
            elif env_var_name=='GEMINI_API_KEY':
                key_way = "https://gemini.google.com/"
            elif env_var_name=='INTERNLM_API_KEY':
                key_way = "https://internlm-chat.intern-ai.org.cn/puyu/api/v1"
            elif env_var_name=='GROQ_API_KEY':
                key_way = "https://api.groq.com/openai/v1"
            elif env_var_name=='MISTRAL_API_KEY':
                key_way = "https://mistral.ai/"
            elif env_var_name=='MOONSHOT_API_KEY':
                key_way = "https://api.moonshot.cn/v1"
            elif env_var_name=='NVIDIA_API_KEY':
                key_way = "https://integrate.api.nvidia.com/"
            elif env_var_name=='OPENAI_COMPATIBILIY_API_KEY':
                key_way = "https://platform.openai.com/docs/overview"
            elif env_var_name=='QWEN_API_KEY':
                key_way = "https://tongyi.aliyun.com/"
            elif env_var_name=='REKA_API_KEY':
                key_way = "https://docs.reka.ai/quick-start"
            elif env_var_name=='SAMBA_API_KEY':
                key_way = "https://community.sambanova.ai/t/looking-for-api-key-and-url-for-sambanova/576"
            elif env_var_name=='TOGETHER_API_KEY':
                key_way = "https://docs.together.ai/docs/quickstart"
            elif env_var_name=='YI_API_KEY':
                key_way = "https://platform.lingyiwanwu.com/docs"
            elif env_var_name=='ZHIPUAI_API_KEY':
                key_way = "https://www.zhipuai.cn/"
        
            if missing_keys:
                raise ValueError(
                    "Missing or empty required API keys in "
                    f"environment variables: {', '.join(missing_keys)}.\n"
                    f"You can obtain the API key from {key_way}"
                )
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def get_system_information():
    r"""Gathers information about the operating system.

    Returns:
        dict: A dictionary containing various pieces of OS information.
    """
    sys_info = {
        "OS Name": os.name,
        "System": platform.system(),
        "Release": platform.release(),
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
        "Platform": platform.platform(),
    }

    return sys_info


def to_pascal(snake: str) -> str:
    """Convert a snake_case string to PascalCase.

    Args:
        snake (str): The snake_case string to be converted.

    Returns:
        str: The converted PascalCase string.
    """
    # Check if the string is already in PascalCase
    if re.match(r'^[A-Z][a-zA-Z0-9]*([A-Z][a-zA-Z0-9]*)*$', snake):
        return snake
    # Remove leading and trailing underscores
    snake = snake.strip('_')
    # Replace multiple underscores with a single one
    snake = re.sub('_+', '_', snake)
    # Convert to PascalCase
    return re.sub(
        '_([0-9A-Za-z])',
        lambda m: m.group(1).upper(),
        snake.title(),
    )


def get_pydantic_major_version() -> int:
    r"""Get the major version of Pydantic.

    Returns:
        int: The major version number of Pydantic if installed, otherwise 0.
    """
    try:
        return int(pydantic.__version__.split(".")[0])
    except ImportError:
        return 0


def get_pydantic_object_schema(pydantic_params: Type[BaseModel]) -> Dict:
    r"""Get the JSON schema of a Pydantic model.

    Args:
        pydantic_params (Type[BaseModel]): The Pydantic model class to retrieve
            the schema for.

    Returns:
        dict: The JSON schema of the Pydantic model.
    """
    return pydantic_params.model_json_schema()


def func_string_to_callable(code: str):
    r"""Convert a function code string to a callable function object.

    Args:
        code (str): The function code as a string.

    Returns:
        Callable[..., Any]: The callable function object extracted from the
            code string.
    """
    local_vars: Mapping[str, object] = {}
    exec(code, globals(), local_vars)
    func = local_vars.get(Constants.FUNC_NAME_FOR_STRUCTURED_OUTPUT)
    return func


def json_to_function_code(json_obj: Dict) -> str:
    r"""Generate a Python function code from a JSON schema.

    Args:
        json_obj (dict): The JSON schema object containing properties and
            required fields, and json format is follow openai tools schema

    Returns:
        str: The generated Python function code as a string.
    """
    properties = json_obj.get('properties', {})
    required = json_obj.get('required', [])

    if not properties or not required:
        raise ValueError(
            "JSON schema must contain 'properties' and 'required' fields"
        )

    args = []
    docstring_args = []
    return_keys = []

    prop_to_python = {
        'string': 'str',
        'number': 'float',
        'integer': 'int',
        'boolean': 'bool',
    }

    for prop in required:
        # if no description, return empty string
        description = properties[prop].get('description', "")
        prop_type = properties[prop]['type']
        python_type = prop_to_python.get(prop_type, prop_type)
        args.append(f"{prop}: {python_type}")
        docstring_args.append(
            f"        {prop} ({python_type}): {description}."
        )
        return_keys.append(prop)

    # extract entity of schema
    args_str = ", ".join(args)
    docstring_args_str = "\n".join(docstring_args)
    return_keys_str = ", ".join(return_keys)

    # function template
    function_code = f'''
def {Constants.FUNC_NAME_FOR_STRUCTURED_OUTPUT}({args_str}):
    r"""Return response with a specified json format.
    Args:
{docstring_args_str}
    Returns:
        Dict: A dictionary containing {return_keys_str}.
    """
    return {{{", ".join([f'"{prop}": {prop}' for prop in required])}}}
    '''

    return function_code


def text_extract_from_web(url: str) -> str:
    r"""Get the text information from given url.

    Args:
        url (str): The website you want to search.

    Returns:
        str: All texts extract from the web.
    """
    try:
        import requests
        from newspaper import Article

        # Request the target page
        article = Article(url)
        article.download()
        article.parse()
        text = article.text

    except requests.RequestException as e:
        text = f"Can't access {url}, error: {e}"

    except Exception as e:
        text = f"Can't extract text from {url}, error: {e}"

    return text


def create_chunks(text: str, n: int) -> List[str]:
    r"""Returns successive n-sized chunks from provided text. Split a text
    into smaller chunks of size n".

    Args:
        text (str): The text to be split.
        n (int): The max length of a single chunk.

    Returns:
        List[str]: A list of split texts.
    """

    chunks = []
    i = 0
    while i < len(text):
        # Find the nearest end of sentence within a range of 0.5 * n
        # and 1.5 * n tokens
        j = min(i + int(1.2 * n), len(text))
        while j > i + int(0.8 * n):
            # Decode the tokens and check for full stop or newline
            chunk = text[i:j]
            if chunk.endswith(".") or chunk.endswith("\n"):
                break
            j -= 1
        # If no end of sentence found, use n tokens as the chunk size
        if j == i + int(0.8 * n):
            j = min(i + n, len(text))
        chunks.append(text[i:j])
        i = j
    return chunks


def is_docker_running() -> bool:
    r"""Check if the Docker daemon is running.

    Returns:
        bool: True if the Docker daemon is running, False otherwise.
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


try:
    if os.getenv("AGENTOPS_API_KEY") is not None:
        from agentops import (
            ToolEvent,
            record,
        )
    else:
        raise ImportError
except (ImportError, AttributeError):
    ToolEvent = None


def agentops_decorator(func):
    r"""Decorator that records the execution of a function if ToolEvent is
    available.

    Parameters:
        func (callable): The function to be decorated.

    Returns:
        callable: The wrapped function which records its execution details.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if ToolEvent:
            tool_event = ToolEvent(name=func.__name__, params=kwargs)
            result = func(*args, **kwargs)
            tool_event.returns = result
            record(tool_event)
            return result
        return func(*args, **kwargs)

    return wrapper


class AgentOpsMeta(type):
    r"""Metaclass that automatically decorates all callable attributes with
    the agentops_decorator,
    except for the 'get_tools' method.

    Methods:
    __new__(cls, name, bases, dct):
        Creates a new class with decorated methods.
    """

    def __new__(cls, name, bases, dct):
        if ToolEvent:
            for attr, value in dct.items():
                if callable(value) and attr != 'get_tools':
                    dct[attr] = agentops_decorator(value)
        return super().__new__(cls, name, bases, dct)


def track_agent(*args, **kwargs):
    r"""Mock track agent decorator for AgentOps."""

    def noop(f):
        return f

    return noop


def handle_http_error(response: requests.Response) -> str:
    r"""Handles the HTTP errors based on the status code of the response.

    Args:
        response (requests.Response): The HTTP response from the API call.

    Returns:
        str: The error type, based on the status code.
    """
    if response.status_code == HTTPStatus.UNAUTHORIZED:
        return "Unauthorized. Check your access token."
    elif response.status_code == HTTPStatus.FORBIDDEN:
        return "Forbidden. You do not have permission to perform this action."
    elif response.status_code == HTTPStatus.NOT_FOUND:
        return "Not Found. The resource could not be located."
    elif response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
        return "Too Many Requests. You have hit the rate limit."
    else:
        return "HTTP Error"


def retry_request(
    func: Callable, retries: int = 3, delay: int = 1, *args: Any, **kwargs: Any
) -> Any:
    r"""Retries a function in case of any errors.

    Args:
        func (Callable): The function to be retried.
        retries (int): Number of retry attempts. (default: :obj:`3`)
        delay (int): Delay between retries in seconds. (default: :obj:`1`)
        *args: Arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        Any: The result of the function call if successful.

    Raises:
        Exception: If all retry attempts fail.
    """
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def download_github_subdirectory(
    repo: str, subdir: str, data_dir: Path, branch="main"
):
    r"""Download subdirectory of the Github repo of
    the benchmark.

    This function downloads all files and subdirectories from a
    specified subdirectory of a GitHub repository and
    saves them to a local directory.

    Args:
        repo (str): The name of the GitHub repository
                in the format "owner/repo".
        subdir (str): The path to the subdirectory
            within the repository to download.
        data_dir (Path): The local directory where
            the files will be saved.
        branch (str, optional): The branch of the repository to use.
            Defaults to "main".
    """
    from tqdm import tqdm

    api_url = (
        f"https://api.github.com/repos/{repo}/contents/{subdir}?ref={branch}"
    )
    headers = {"Accept": "application/vnd.github.v3+json"}
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    files = response.json()
    os.makedirs(data_dir, exist_ok=True)

    for file in tqdm(files, desc="Downloading"):
        file_path = data_dir / file["name"]

        if file["type"] == "file":
            file_url = file["download_url"]
            file_response = requests.get(file_url)
            with open(file_path, "wb") as f:
                f.write(file_response.content)
        elif file["type"] == "dir":
            download_github_subdirectory(
                repo, f'{subdir}/{file["name"]}', file_path, branch
            )


def generate_prompt_for_structured_output(
    response_format: Optional[Type[BaseModel]],
    user_message: str,
) -> str:
    """
    This function generates a prompt based on the provided Pydantic model and
    user message.

    Args:
        response_format (Type[BaseModel]): The Pydantic model class.
        user_message (str): The user message to be used in the prompt.

    Returns:
        str: A prompt string for the LLM.
    """
    if response_format is None:
        return user_message

    json_schema = response_format.model_json_schema()
    sys_prompt = (
        "Given the user message, please generate a JSON response adhering "
        "to the following JSON schema:\n"
        f"{json_schema}\n"
        "Make sure the JSON response is valid and matches the EXACT structure "
        "defined in the schema. Your result should only be a valid json "
        "object, without any other text or comments.\n"
    )
    user_prompt = f"User message: {user_message}\n"

    final_prompt = f"""
    {sys_prompt}
    {user_prompt}
    """
    return final_prompt

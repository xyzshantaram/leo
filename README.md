# leo

### a gemini client written in Python 3. Aiming to use only the standard library as far as possible.

#### (UNIX-only, Windows support with WSL)    

#### Instructions for use:
0) clone this repo.
1) set options to your preferences in the `config.json` file.
    * `wrap_text` specifies whether to wrap text beyond a certain width.
    * `wrap_margin` specifies what that width should be.
    * `homepage` is a page to load by default if no URL is specified.
    * `cert_path` is a certificate file.

_Note_: You can specify an alternate config file with the `--config` option.

2) ```leo/main.py --url <url>```. If you do not specify a URL, the homepage set in `config.json` is loaded. If no homepage is set, you will be prompted for a URL.  

3) if you'd like to connect providing a client certificate (required by certain Gemini servers), set the "cert_path" option in `config.json` to a valid path to a cert file.  

4) Links are preceded by a number that is underlined and violet in colour. Type in the number of the link at the `(URL/Num):` prompt in order to navigate to a specific link, or type in a URL.  

5) Type `reload` to refresh a page.  

6) `back` takes you one page back.  

7) View a short listing of these commands anytime by typing `help`.  

8) Type ```exit``` or ```quit``` to exit leo.  

#### Features:
* Fully implements Gemini spec
* Passes torture tests at gemini://gemini.conman.org/test/torture/ (Save for the final few Unicode ones, but I cba to read a spec)
* formatted text output with arbitrary wrapping support
* The lack of tabbed browsing is a feature
* Comes with a built-in pager!

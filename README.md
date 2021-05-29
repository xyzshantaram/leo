# leo

## a gemini client written in Python 3.

#### (UNIX-only, Windows support with WSL)    

### Instructions for use:
0) `$ pip install leo-gmi`
1) `$ leo --copy-config` to create a config file in `$XDG_CONFIG_HOME/leo` (falls back to `~/.config/leo`)
* If you don't want to put the config file in either of those places, `leo --print-config` prints out the config that you can then supply to leo with the `--config` option.
2) set options to your preferences in the `config.json` file.
    * `wrap_text` specifies whether to wrap text beyond a certain width.
    * `wrap_margin` specifies what that width should be.
    * `homepage` is a page to load by default if no URL is specified.
    * `cert_path` is the path to a certificate file.

    _**Note**: You can specify an alternate config file with the `--config` option._

3) ```$ leo --url <url>```. If you do not specify a URL, the homepage set in `config.json` is loaded. If no homepage is set, you will be prompted for a URL.  

4) if you'd like to connect providing a client certificate (required by certain Gemini servers), set the `"cert_path"` option in your config file to a valid path to a cert file.

5) Links are preceded by a number that is underlined and violet in colour. Type in the number of the link at the `(URL/Num):` prompt in order to navigate to a specific link, or type in a URL.  

6) Type `reload` to refresh a page. `reload hard` redownloads the page.  

7) `back` takes you one page back.  

8) Type `help` at any time to view a listing of these and other useful commands.

9) Type ```exit``` or ```quit``` to exit leo.  

#### Features:
* Only uses the python standard library
* Fully implements Gemini spec
* Passes torture tests at gemini://gemini.conman.org/test/torture/ (Save for the final few Unicode ones, but I cba to read a spec)
* formatted text output with arbitrary wrapping support
* Comes with a built-in pager!
* Lets you save a list of URLs to a file for further viewing / opening in another window

### Contributing

Fork the repo and make a PR! That's all :) You can alternatively send me an e-mail with your patch.
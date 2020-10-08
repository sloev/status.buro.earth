import os
import glob
import string

path = os.path.dirname(__file__)
templates = {
    fn.rsplit("/", 1)[1].replace(".", "_"): string.Template(open(fn).read())
    for fn in glob.glob(path + "/*.html")
}
css_files = {fn.rsplit("/", 1)[1]: fn for fn in glob.glob(path + "/*.css")}

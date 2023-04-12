#!/usr/bin/env python

from email.mime import image
from    pathlib             import Path
from    argparse            import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter

from    chris_plugin        import chris_plugin, PathMapper
from    typing              import Callable, Any, Iterable, Iterator
from    pftag               import pftag
from    pflog               import pflog
from    concurrent.futures  import ThreadPoolExecutor, ProcessPoolExecutor
from    functools           import partial
import  os, sys
import  pudb
import  pydicom
os.environ['XDG_CONFIG_HOME'] = '/tmp'  # For root/non root container sanity

from    PIL                 import Image
import  numpy               as      np
from    loguru              import logger
LOG             = logger.debug
logger_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> │ "
    "<level>{level: <5}</level> │ "
    "<yellow>{name: >28}</yellow>::"
    "<cyan>{function: <30}</cyan> @"
    "<cyan>{line: <4}</cyan> ║ "
    "<level>{message}</level>"
)
logger.remove()
logger.opt(colors = True)
logger.add(sys.stderr, format=logger_format)



__version__ = '2.0.0'

DISPLAY_TITLE = r"""
       _           _ _                                     _
      | |         | (_)                                   | |
 _ __ | |______ __| |_  ___ ___  _ __ ___  _ __ ___   __ _| | _____
| '_ \| |______/ _` | |/ __/ _ \| '_ ` _ \| '_ ` _ \ / _` | |/ / _ \
| |_) | |     | (_| | | (_| (_) | | | | | | | | | | | (_| |   <  __/
| .__/|_|      \__,_|_|\___\___/|_| |_| |_|_| |_| |_|\__,_|_|\_\___|
| |
|_|
"""


parser = ArgumentParser(description='''
    A ChRIS DS plugin that "makes" a new DICOM file from an image and
    an exemplar DICOM.
    ''', formatter_class=ArgumentDefaultsHelpFormatter)

parser.add_argument(  '--filterIMG',
                    dest        = 'filterIMG',
                    type        = str,
                    help        = 'Input image file filter',
                    default     = '**/*.png')
parser.add_argument(  '--filterDCM',
                    dest        = 'filterDCM',
                    type        = str,
                    help        = 'Input DICOM file filter',
                    default     = '**/*.dcm')
parser.add_argument(  '--outputSubDir',
                    dest        = 'outputSubDir',
                    default     = '',
                    type        = str,
                    help        = 'if specified, save all output here (relative to outputdir)')
parser.add_argument(  '--pftelDB',
                    dest        = 'pftelDB',
                    default     = '',
                    type        = str,
                    help        = 'optional pftel server DB path')
parser.add_argument("--thread",
                    help        = "use threading to branch in parallel",
                    dest        = 'thread',
                    action      = 'store_true',
                    default     = False)
parser.add_argument('--version',
                    action      = 'version',
                    version     = f'%(prog)s {__version__}')

def preamble_show(options: Namespace) -> None:
    """
    Just show some preamble "noise" in the output terminal
    """
    LOG(DISPLAY_TITLE)
    LOG("plugin arguments...")
    for k,v in options.__dict__.items():
         LOG("%25s:  [%s]" % (k, v))
    LOG("")
    LOG("base environment...")
    for k,v in os.environ.items():
         LOG("%25s:  [%s]" % (k, v))
    LOG("")

def image_intoDICOMinsert(image: Image.Image, ds: pydicom.Dataset) -> pydicom.Dataset:
    """
    Insert the "image" into the DICOM chassis "ds" and update/adapt
    DICOM tags where necessary. Also create a new

        SeriesInstanceUID
        SOPInstanceUID

    Args:
        image (Image.Image): an input image
        ds (pydicom.Dataset): a DICOM Dataset to house the image

    Returns:
        pydicom.Dataset: a DICOM Dataset with the new image
    """
    def npimage_get(image):
        interpretation:str  = ""
        samplesPerPixel:int = 1
        if 'RGB' in image.mode:
            np_image = np.array(image.getdata(), dtype=np.uint8)[:,:3]
            interpretation  = 'RGB'
            samplesPerPixel = 3
        else:
            np_image = np.array(image.getdata(), dtype = np.uint8)
            interpretation  = 'MONOCHROME1'
            samplesPerPixel = 1
        return np_image, interpretation, samplesPerPixel

    np_image, \
    ds.PhotometricInterpretation,   \
    ds.SamplesPerPixel              = npimage_get(image)
    ds.Rows                         = image.height
    ds.Columns                      = image.width
    ds.SamplesPerPixel              = 3
    ds.BitsStored                   = 8
    ds.BitsAllocated                = 8
    ds.HighBit                      = 7
    ds.PixelRepresentation          = 0
    ds.PixelData                    = np_image.tobytes()
    ds.SeriesInstanceUID            = pydicom.uid.generate_uid()
    ds.SOPInstanceUID               = pydicom.uid.generate_uid()
    return ds

def doubly_map(x: PathMapper, y: PathMapper) -> Iterable[tuple[Path, Path, Path, Path]]:
    """
    Combine two Mappers and yield the combined results.

    Args:
        x (PathMapper): first set
        y (PathMapper): second set

    Yields:
        Iterator[Iterable[tuple[Path, Path, Path, Path]]]: a quartuplet of paths
    """
    for pair_x, pair_y in zip(x, y):
        input_x, output_x = pair_x
        input_y, output_y = pair_y
        yield input_x, output_x, input_y, output_y

def tree2flat_path_mapping(inputdir:Path, outputdir:Path,
                           input_glob:str, output_suffix:str = "")\
    -> Iterator[tuple[Path, Path]]:
    """
    Collapses the outputdir to single location, not preserving the input
    tree structure.

    Args:
        inputdir (Path): input directory path
        outputdir (Path): output directory path
        input_glob (str): input file search glob
        output_suffix (str, optional): optional output suffix. Defaults to "".

    Yields:
        Iterator[tuple[Path, Path]]: A mapper
    """
    for input_file in inputdir.glob(input_glob):
        output_file: Path = (outputdir / input_file.name).with_suffix(output_suffix)
        yield input_file, output_file

def tree2tree_path_mapping(inputdir: Path, outputdir: Path,
                           input_glob: str, output_suffix:str = "")\
    -> Iterator[tuple[Path, Path]]:
    """
    A thin fall-through to the default PathMapper

    Args:
        inputdir (Path): input directory path
        outputdir (Path): output directory path
        input_glob (str): input file search glob
        output_suffix (str, optional): optional output suffix. Defaults to "".

    Yields:
        Iterator[tuple[Path, Path]]: A mapper
    """
    return iter(
        PathMapper.file_mapper(
            inputdir, outputdir, glob=input_glob, suffix=output_suffix
        )
    )

def env_setupAndCheck(options: Namespace, inputdir: Path, outputdir: Path)\
    -> dict[str, Any]:
    """
    Setup the "environment", i.e. generate lists of input and output
    files to process. Also, check that the input lists have the same
    length and return the paths and status to a caller.


    Args:
        options (Namespace): CLI options (needed to resolve output (sub) dir)
        inputdir (Path): input directory path
        outputdir (Path): output directory path

    Returns:
        dict[str, Any]: the status and dictionary of paths
    """
    d_paths:dict[str, Any] = \
        allIO_checkInputLengths(
            allIO_findExplicitly(options, inputdir, outputdir)
        )
    if not d_paths['status']:
        LOG('Path length check failed! DICOM file list not equal length to IMG file list')
    return d_paths

def allIO_checkInputLengths(d_IO:dict[str, list]) -> dict[str, Any]:
    """
    Simply check that the lengths of the lists for the
    DICOM and image lists are the same.

    Args:
        d_IO (dict[str, list]): the result from allIO_unspool()

    Returns:
        dict[str, Any]: the input with a bool status field.
    """
    b_status:bool = True if len(d_IO['inputDCM']) == len(d_IO['inputIMG']) \
                    else False
    d_check:dict[str, Any]     = {
        'status':   b_status,
        'd_IO':     d_IO
    }
    return d_check

def allIO_findExplicitly(options: Namespace, inputdir: Path, outputdir: Path) \
    -> dict[str, list[Path]]:
    """
    Explicitly process a double PathMapper into lists, and return the
    sorted lists. Lists are sorted so as to assure (hopefully) that
    a given DICOM file lines up correctly with a given image file to
    that is to serve as its embedded image.

    Args:
        options (Namespace): CLI options namespace
        inputdir (Path): the plugin inputdir
        outputdir (Path): the plugin outputdir

    Returns:
        dict[str, list[Path]]: a dictionary of sorted incoming and outgoing
                               path lists.
    """

    d_ret:dict[str, list[Path]] = {
        'inputDCM'          : [],
        'inputIMG'          : [],
        'outputDCM'         : [],
        'outputIMG'         : [],
    }
    l_inputDCM:list         = []
    l_inputIMG:list         = []
    l_outputDCM:list        = []
    l_outputIMG:list        = []
    Mapper:Callable[[Path, Path, str, str], Iterator[tuple[Path, Path]]] = tree2tree_path_mapping
    if options.outputSubDir:
        outputdir           = outputdir / Path(options.outputSubDir)
        outputdir.mkdir(parents = True, exist_ok = True)
        Mapper              = tree2flat_path_mapping
    mapperDCM: PathMapper   = \
        Mapper(inputdir, outputdir, input_glob=options.filterDCM, output_suffix='.dcm')
    mapperIMG: PathMapper   = \
        Mapper(inputdir, outputdir, input_glob=options.filterIMG, output_suffix='.dcm')
    for input_fileDCM, output_fileDCM, input_fileIMG, output_fileIMG in \
        doubly_map(mapperDCM, mapperIMG):
        l_inputDCM.append(input_fileDCM)
        l_inputIMG.append(input_fileIMG)
        l_outputDCM.append(output_fileDCM)
        l_outputIMG.append(output_fileIMG)
    d_ret['inputDCM']      = [Path(y) for y in sorted([str(x) for x in l_inputDCM])]
    d_ret['inputIMG']      = [Path(y) for y in sorted([str(x) for x in l_inputIMG])]
    d_ret['outputDCM']     = [Path(y) for y in sorted([str(x) for x in l_outputDCM])]
    d_ret['outputIMG']     = [Path(y) for y in sorted([str(x) for x in l_outputIMG])]
    return d_ret

def files_unspool(d_paths:dict[str, Any]) -> Iterator[tuple[Path, Path, Path]]:
    """
    This implements an Iterator over the lists passed in d_paths, and is ultimately
    used as a mapper in the main method.

    Args:
        d_paths (dict[str, Any]): a dictionary of lists of files to process

    Yields:
        Iterator[tuple[Path, Path, Path]]: DICOM input, image input, and DICOM output
    """
    for dcm_in, img_in, dcm_out in zip( d_paths['d_IO']['inputDCM'],
                                        d_paths['d_IO']['inputIMG'],
                                        d_paths['d_IO']['outputDCM']):
        yield dcm_in, img_in, dcm_out

def imageNames_areSame(imgfile:Path, dcmfile:Path) -> bool:
    """
    Simply checks that the "stems", i.e. the file names w/o extensions or
    path prefices of the two input path files are the same

    Args:
        imgfile (Path): the image file
        dcmfile (Path): the DICOM file

    Returns:
        bool: Do they both have the same file stem?
    """
    return True if imgfile.stem == dcmfile.stem else False

def imagePaths_process(*args) -> None:
    """
    The input *args is a tuple that contains three
    file (Paths) to process. Since this method can
    be called either from a ProcessPoolExecutor mapper
    or directly, the try/catch is needed to correctly
    unpack the arguments in either case.
    """
    try:
        dcm_in:Path  = args[0][0]
        img_in:Path  = args[0][1]
        dcm_out:Path = args[0][2]
    except:
        dcm_in:Path  = args[0]
        img_in:Path  = args[1]
        dcm_out:Path = args[2]

    if imageNames_areSame(img_in, dcm_in):
        image:Image.Image       = Image.open(str(img_in))
        DICOM:pydicom.Dataset   = pydicom.dcmread(str(dcm_in))
        LOG("Processing %s using %s" % (dcm_in.name, img_in.name))
        image_intoDICOMinsert(image, DICOM).save_as(str(dcm_out))
        LOG("Saved %s" % dcm_out)

@chris_plugin(
    parser          = parser,
    title           = 'DICOM image make',
    category        = '',                   # ref. https://chrisstore.co/plugins
    min_memory_limit= '100Mi',              # supported units: Mi, Gi
    min_cpu_limit   = '1000m',              # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit   = 0                     # set min_gpu_limit=1 to enable GPU
)
@pflog.tel_logTime(
    event           = 'dicommake',
    log             = 'Make output/final DICOM from images with measurements'
)
def main(options: Namespace, inputdir: Path, outputdir: Path) -> int:
    """
    The main entry point for this plugin/app. Mostly this function simply
    decides whether or not to call the imagePaths_process() function in
    series or in parallel.

    Take a look at imagePaths_process() to better understand the logic.

    Args:
        options (Namespace): the CLI options
        inputdir (Path): the input directory path containing data to process
        outputdir (Path): the output directory where results are saved

    Returns:
        int: 0 here means success.
    """
    d_paths:dict[str, Any] = env_setupAndCheck(options, inputdir, outputdir)
    mapper: Iterator[tuple[Path, Path, Path]] = files_unspool(d_paths)

    if int(options.thread):
        # While the "thread" implies "threading", we actually use
        # a ProcessPoolExecutor since the single threaded GIL actually
        # does not perform python file loading/saving in parallel.
        with ProcessPoolExecutor() as pool:
            results: Iterator[None]     = pool.map(imagePaths_process, mapper)

        # raise any Exceptions which happened in threads
        for _ in results:
            pass
    else:
        for dcm_in, img_in, dcm_out in mapper:
            imagePaths_process(dcm_in, img_in, dcm_out)

    return 0

if __name__ == '__main__':
    sys.exit(main())

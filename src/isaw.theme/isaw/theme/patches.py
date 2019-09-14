import os
import six

from cgi import escape
from xml.sax.saxutils import quoteattr
from ZODB.blob import Blob
from ZODB.blob import BlobFile

from pyexif import ExifEditor
from pyexif import _runproc
from tempfile import mkdtemp

from OFS.Image import Image
from Products.Archetypes.Field import ImageField
from Products.PluginIndexes.UUIDIndex.UUIDIndex import UUIDIndex
from Products.TinyMCE.utility import TinyMCE
from plone.app.imaging import traverse
from plone.app.blob import scale as blob_scale
from plone.namedfile.scaling import ImageScale
from plone.scale import scale


_marker = object()

# Monkey-patch the TinyMCE utility to return a wildcard allowing all
# tags and attributes, so sanitization happens on save only (we hope).
TinyMCE.getValidElements = lambda self: {'*': ['*']}


def allow_not_uuid():
    UUIDIndex.query_options = tuple(UUIDIndex.query_options) + ('not',)


def _wcag_tag(self, instance, scale=None, height=None, width=None, alt=None,
              css_class=None, title=None, **kwargs):
    """"Accept title as parameter, but do not use in img tag, per WCAG"""
    image = self.getScale(instance, scale=scale)
    if image:
        img_width, img_height = self.getSize(instance, scale=scale)
    else:
        img_height = 0
        img_width = 0

    if height is None:
        height = img_height
    if width is None:
        width = img_width

    url = instance.absolute_url()
    if scale:
        url += '/' + self.getScaleName(scale)
    else:
        url += '/' + self.getName()

    if not alt:
        alt = instance.Title()

    values = {'src': url,
              'alt': escape(alt, quote=True),
              'height': height,
              'width': width,
              }

    result = '<img src="%(src)s" alt="%(alt)s" '\
                'height="%(height)s" width="%(width)s"' % values

    if css_class is not None:
        result = '%s class="%s"' % (result, css_class)

    for key, value in kwargs.items():
        if value:
            result = '%s %s="%s"' % (result, key, value)

    return '%s />' % result


def img_tag_no_title():
    ImageField.tag = _wcag_tag


def _wcag_ofs_tag(self, height=None, width=None, alt=None,
        scale=0, xscale=0, yscale=0, css_class=None, title=None, **args):

    if height is None: height=self.height
    if width is None:  width=self.width

    xdelta = xscale or scale
    ydelta = yscale or scale

    if xdelta and width:
        width =  str(int(round(int(width) * xdelta)))
    if ydelta and height:
        height = str(int(round(int(height) * ydelta)))

    result='<img src="%s"' % (self.absolute_url())

    if alt is None:
        alt=getattr(self, 'alt', '')
    result = '%s alt="%s"' % (result, escape(alt, 1))

    if height:
        result = '%s height="%s"' % (result, height)

    if width:
        result = '%s width="%s"' % (result, width)

    if css_class is not None:
        result = '%s class="%s"' % (result, css_class)

    for key in args.keys():
        value = args.get(key)
        if value:
            result = '%s %s="%s"' % (result, key, value)

    return '%s />' % result


def ofs_img_tag_no_title():
    Image.tag = _wcag_ofs_tag


def _wcag_named_file_image_tag(self, height=_marker, width=_marker, alt=_marker,
        css_class=None, title=_marker, **kwargs):
    """Create a tag including scale
    """
    if height is _marker:
        height = getattr(self, 'height', self.data._height)
    if width is _marker:
        width = getattr(self, 'width', self.data._width)

    if alt is _marker:
        alt = getattr(self.context, 'alt', '')

    values = [
        ('src', self.url),
        ('alt', alt),
        ('height', height),
        ('width', width),
        ('class', css_class),
    ]
    values.extend(kwargs.items())

    parts = ['<img']
    for k, v in values:
        if v is None:
            continue
        if isinstance(v, int):
            v = str(v)
        elif isinstance(v, str):
            v = unicode(v, 'utf8')
        parts.append(u'{0}={1}'.format(k, quoteattr(v)))
    parts.append('/>')

    return u' '.join(parts)


def named_file_image_tag():
    ImageScale.tag =  _wcag_named_file_image_tag


def preserve_exif():

    EXIF_NON_WRITEABLE = [
        'ThumbnailOffset',
        'SlicesGroupName',
        'ColorSpaceData',
        'MIMEType',
        'ProgressiveScans',
        'FileAccessDate',
        'ProfileID',
        'ProfileDescription',
        'ThumbnailImage',
        'MeasurementIlluminant',
        'RedTRC',
        'ViewingCondIlluminantType',
        'GreenTRC',
        'PrimaryPlatform',
        'HyperfocalDistance',
        'ProfileFileSignature',
        'URL_List',
        'PhotoshopThumbnail',
        'SourceFile',
        'ProfileCMMType',
        'MeasurementGeometry',
        'DeviceModel',
        'ConnectionSpaceIlluminant',
        'DeviceModelDesc',
        'FileType',
        'FOV',
        'PhotoshopFormat',
        'ScaleFactor35efl',
        'DeviceManufacturer',
        'ExifToolVersion',
        'CurrentIPTCDigest',
        'PrintPosition',
        'MeasurementObserver',
        'ProfileDateTime',
        'ProfileCreator',
        'FileTypeExtension',
        'Technology',
        'ThumbnailLength',
        'CMMFlags',
        'ProfileClass',
        'RenderingIntent',
        'GPSPosition',
        'ShutterSpeed',
        'ColorTransform',
        'DCTEncodeVersion',
        'ReaderName',
        'Megapixels',
        'HasRealMergedData',
        'PrintScale',
        'FileInodeChangeDate',
        'WriterName',
        'MeasurementFlare',
        'PixelAspectRatio',
        'ColorComponents',
        'MediaWhitePoint',
        'ViewingCondIlluminant',
        'BlueMatrixColumn',
        'APP14Flags0',
        'APP14Flags1',
        'DeviceAttributes',
        'MediaBlackPoint',
        'Aperture',
        'CircleOfConfusion',
        'MeasurementBacking',
        'PrintStyle',
        'DeviceMfgDesc',
        'LightValue',
        'DateTimeCreated',
        'BlueTRC',
        'ViewingCondDesc',
        'FocalLength35efl',
        'ViewingCondSurround',
        'GreenMatrixColumn',
        'Luminance',
        'NumSlices',
        'ProfileVersion',
        'FileSize',
        'RedMatrixColumn',
        'EncodingProcess',
        'ProfileConnectionSpace',
        'JFIFVersion',
    ]

    def exif_setTags(editor, tags_dict):
        vallist = []
        for tag in tags_dict:
            if tag in EXIF_NON_WRITEABLE:
                continue
            val = tags_dict[tag]
            if isinstance(val, six.string_types):
                val = val.replace('"', '\\"')
            vallist.append('-{0}="{1}"'.format(tag, val))
        valstr = " ".join(vallist)
        cmd = """exiftool {editor._optExpr} {valstr} "{editor.photo}" """.format(**locals())
        out = _runproc(cmd, editor.photo)

    def _preserve_exif(orig_image, new_image):
        tmp_dir = mkdtemp()
        exiftool_path = os.path.join(tmp_dir, 'plone_image')
        old_file = open(exiftool_path, "wb")
        old_file.write(orig_image)
        old_exif = ExifEditor(exiftool_path)
        old_exif_tags = old_exif.getDictTags()
        old_file.close()
        new_file = open(exiftool_path, "wb")
        new_file.write(new_image)
        new_file.close()
        new_exif = ExifEditor(exiftool_path)
        exif_setTags(new_exif, old_exif_tags)
        new_file = open(exiftool_path, 'rb')
        image = new_file.read()
        new_file.close()
        os.remove(exiftool_path)
        os.rmdir(tmp_dir)
        return image

    def scaleImage(image, result=None, **parameters):
        """Update image scalers to transfer exif data if available"""
        new_image, format, size = orig_scaleImage(image, result=None, **parameters)

        if isinstance(image, BlobFile):
            image.seek(0)
            image = image.read()

        new_image = _preserve_exif(image, new_image)
        if result and hasattr(result, 'write'):
            result.write(new_image)
            result.seek(0)
        else:
            result = new_image
        return result, format, size

    def blob_create(self, context, **parameters):
        wrapper = self.field.get(context)
        if wrapper:
            try:
                blob = Blob()
                result = blob.open('w')
                _, format, dimensions = scaleImage(wrapper.getBlob().open('r'),
                                                   result=result, **parameters)
                result.close()
                return blob, format, dimensions
            except IOError:
                return

    def createScale(self, instance, scale, width, height, data=None):
        """Preserve EXIF on new images"""
        try:
            result = orig_createScale(self, instance, scale, width, height, data)
        except IOError: # probably bad image type
            result = None
        if result:
            new_image = result['data']
            orig_image = self.context.getRaw(instance).data
            new_image = _preserve_exif(orig_image, new_image)
            result['data'] = new_image
        return result

    orig_scaleImage = scale.scaleImage
    blob_scale.BlobImageScaleFactory.create = blob_create
    orig_createScale = traverse.DefaultImageScaleHandler.createScale
    traverse.DefaultImageScaleHandler.createScale = createScale

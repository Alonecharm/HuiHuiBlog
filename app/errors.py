# coding=utf-8
# author = matt.cai(cysnake4713@gmail.com)
from webargs import ValidationError


class BaseError(ValidationError):
    status_code = 400
    error_code = 40001
    error_message = '内部错误，不应该被抛出'
    extra_msg = ''

    def __init__(self, extra_msg=None, **kwargs):
        self.extra_msg = extra_msg
        super(BaseError, self).__init__(status_code=self.status_code, message={
            'error_code': self.error_code,
            'error_message': self.__doc__ or self.error_message,
            'extra_msg': extra_msg,
        }, **kwargs)

    def to_dict(self):
        return {
            "error_code": self.error_code,
            "error_message": self.__doc__ or self.error_message,
            "extra_msg": self.extra_msg,
        }


class UnKnownError(BaseError):
    status_code = 422
    error_code = 40000
    error_message = '未知错误，不应该被抛出'


class BasePageRangeTooLargeError(BaseError):
    status_code = 400
    error_code = 40002
    error_message = '每页显示数量大于限制'


class BaseBooleanTypeError(BaseError):
    error_code = 40003
    error_message = 'boolean类型参数必须是true | false'


class BaseIntegerTypeError(BaseError):
    error_code = 40004
    error_message = '必须是整型数字'


class BaseStringTypeError(BaseError):
    error_code = 40005
    error_message = '不是一个有效的字符串'


class BaseDictTypeError(BaseError):
    error_code = 40006
    error_message = '必须是一个字典'


class BaseListTypeError(BaseError):
    error_code = 40007
    error_message = '必须是一个列表'


class BaseFloatTypeError(BaseError):
    error_code = 40008
    error_message = '必须是一个浮点数'


class BaseDecimalTypeError(BaseError):
    error_code = 40009
    error_message = '必须是一个高精度数'


class BaseUUIDTypeError(BaseError):
    error_code = 40010
    error_message = '不是有效的uuid编码'


class BaseEmailTypeError(BaseError):
    error_code = 40011
    error_message = '不是一个有效的邮件格式'


class BaseDatetimeTypeError(BaseError):
    error_code = 40012
    error_message = '不是一个有效的日期时间格式'


class BaseDateTypeError(BaseError):
    error_code = 400121
    error_message = '不是一个有效的日期格式'


class BaseNullError(BaseError):
    error_code = 40013
    error_message = '不能为null'


class BaseRequiredError(BaseError):
    error_code = 40014
    error_message = '不能为空'


class BaseCurrencyError(BaseError):
    error_code = 40015
    error_message = '不是有效的货币单位'


class BaseCountryError(BaseError):
    error_code = 40016
    error_message = '不是有效的国家编码'


class BaseUrlError(BaseError):
    error_code = 40017
    error_message = '不是有效的url格式'


class BasePhoneError(BaseError):
    error_code = 40018
    error_message = '不是有效的电话格式'


class BaseNoLoginError(BaseError):
    status_code = 401
    error_code = 40101
    error_message = '未登录，无法访问'


class BaseSubSystemError(BaseError):
    error_code = 40201
    error_message = '不是有效的子系统类型'


class BaseModuleNameError(BaseError):
    error_code = 40202
    error_message = '不是有效的子模块类型'


class PermissionForbiddenError(BaseError):
    error_code = 30001

    def __init__(self, name):
        self.error_message = '授权：{} 禁止访问'.format(name)

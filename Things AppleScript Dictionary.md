# APPLESCRIPT TYPES  
**AppleScript Types**Built-in AppleScript value types.  
# DESCRIPTION  
This information, about the native built-in AppleScript datatypes, is not part of the dictionary you are viewing; a dictionary does not need to define these types, because they are built in to AppleScript! Rather, it has been provided, as a public service, by this program.  
# CLASSES  
# date  
**date** *\(noun\), pl* **dates**A date-time value.  
# DESCRIPTION  
A *date* is a date-time, stored internally as a number of seconds since some fixed initial reference date. A date can be mutated in place, and is one of the classes for which set and copy behave differently.  
A literal date is an object string specifier. In constructing a date, you may use any string value that can be interpreted as a date, a time, or a date-time. AppleScript supplies missing values such as today’s date \(if you give only a time\) or midnight \(if you give only a date\). To form a date object for the current date-time, use the current date scripting addition command.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
date string  
get  
[text](typeref:///text)  
The date portion of a date, as text.  
day  
get  
[integer](typeref:///integer)  
The day of the month of a date.  
month  
get  
[month](typeref:///month)  
The month of a date. A constant \(not a string or a number\); however, this constant can be coerced to a string or a number, and can be set using a number.  
short date string  
get  
[text](typeref:///text)  
The date portion of a date, as text \(in a more abbreviated format than the date string\).  
time  
get  
[integer](typeref:///integer)  
The number of seconds since midnight of a date-time’s day.  
time string  
get  
[text](typeref:///text)  
The time portion of a date, as text.  
weekday  
get  
[weekday](typeref:///weekday)  
The day of a week of a date. A constant \(not a string or number\); however, this constant can be coerced to a string or a number.  
year  
get  
[integer](typeref:///integer)  
The year of a date.  
# WHERE USED  
The **date** class is used in the following ways\:  
**activation date** property of the **[to do](typeref:///to%20do)** class/record  
**cancellation date** property of the **[to do](typeref:///to%20do)** class/record  
**completion date** property of the **[to do](typeref:///to%20do)** class/record  
**creation date** property of the **[to do](typeref:///to%20do)** class/record  
**due date** property of the **[to do](typeref:///to%20do)** class/record  
**due date** property of the **[item details](typeref:///item%20details)** class/record  
**for** parameter of the **[schedule](commandref:///schedule)** command/event  
**modification date** property of the **[to do](typeref:///to%20do)** class/record  
# file  
**file** *\(noun\), pl* **files***\[synonyms\:* **file specification***\]*A reference to a file or a folder on disk.  
# DESCRIPTION  
A *file* object is a reference to a file or folder on disk. To construct one, use an object string specifier, the word file followed by a pathname string value\:  
file "MyDisk\:Users\:myself\:"  
If you try to assign a file object specifier to a variable, or return it as a value, you’ll get a runtime error. Instead, you must generate a reference to the file object, like this\:  
set x to a reference to file "MyDisk\:Users\:myself\:"  
You can also construct, and sometimes applications or scripting addition commands \(such as choose file name\) will return, a file specified by its POSIX path\:  
POSIX file "/Users/myself/"  
Such a specifier is actually of a different class, «class furl» \(a file URL\). This class can be difficult to distinguish from the basic file object type, but it is in fact different, and it *can* be assigned to a variable.  
At runtime, when a file specifier is handed to some command, either the item must exist, or, if the command proposes to create it, everything in the path must exist except for the last element, the name of the item you’re about to create. Thus a file specifer can be used to create a file or folder; an [alias](ref:///alias) can’t be used to do that, and this is a major difference between the two types.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
POSIX path  
get  
[text](typeref:///text)  
The POSIX path of the file.  
# WHERE USED  
The **file** class is used in the following ways\:  
direct parameter to the **[print](commandref:///print)** command/event  
# month  
**month** *\(noun\), pl* **months**A calendar month.  
# WHERE USED  
The **month** class is used in the following ways\:  
**month** property of the **[date](typeref:///date)** class/record  
# weekday  
**weekday** *\(noun\), pl* **weekdays**A weekday.  
# WHERE USED  
The **weekday** class is used in the following ways\:  
**weekday** property of the **[date](typeref:///date)** class/record  
# TYPES  
# any  
**any** *\(type\)*Anything.  
# DESCRIPTION  
The *any* datatype is used as a wildcard type in a dictionary, usually because the creators of the dictionary have found it impractical to list explicitly the actual possible types of a value. It isn’t used in AppleScript programming.  
# WHERE USED  
The **any** type is used in the following ways\:  
direct parameter to the **[exists](commandref:///exists)** command/event  
**contents** property of the **[selection-object](typeref:///selection-object)** class/record  
# boolean  
**boolean** *\(type\)*A true or false value.  
# DESCRIPTION  
A *boolean* is a datatype consisting of exactly two possible values, *true* and *false*, and is typically used wherever this kind of binary value possibility is appropriate. It results from comparisons, and is used in conditions. The integers 1 and 0 can be coerced to a boolean, and vice versa. The strings "true" and "false" can be coerced to a boolean, and vice versa.  
class of true -- **boolean**  
class of \(1 \< 2\) -- **boolean**  
# WHERE USED  
The **boolean** type is used in the following ways\:  
result of **[exists](commandref:///exists)** command  
**closeable** property of the **[window](typeref:///window)** class/record  
**collapsed** property of the **[area](typeref:///area)** class/record  
**collating** property of the **[print settings](typeref:///print%20settings)** class/record  
**frontmost** property of the **[application](typeref:///application)** class/record  
**minimizable** property of the **[window](typeref:///window)** class/record  
**minimized** property of the **[window](typeref:///window)** class/record  
**print dialog** parameter of the **[print](commandref:///print)** command/event  
**resizable** property of the **[window](typeref:///window)** class/record  
**visible** property of the **[window](typeref:///window)** class/record  
**with autofill** parameter of the **[show quick entry panel](commandref:///show%20quick%20entry%20panel)** command/event  
**zoomable** property of the **[window](typeref:///window)** class/record  
**zoomed** property of the **[window](typeref:///window)** class/record  
# integer  
**integer** *\(type\)*An integer value.  
# DESCRIPTION  
The *integer* datatype is one of the two basic [number](ref:///number) types; the other is [real](ref:///real). An integer is a whole number, without a decimal point. It must lie between 536870911 and –536870912 inclusive.  
# WHERE USED  
The **integer** type is used in the following ways\:  
result of **[count](commandref:///count)** command  
**copies** property of the **[print settings](typeref:///print%20settings)** class/record  
**day** property of the **[date](typeref:///date)** class/record  
**ending page** property of the **[print settings](typeref:///print%20settings)** class/record  
**id** property of the **[window](typeref:///window)** class/record  
**index** property of the **[window](typeref:///window)** class/record  
**pages across** property of the **[print settings](typeref:///print%20settings)** class/record  
**pages down** property of the **[print settings](typeref:///print%20settings)** class/record  
**starting page** property of the **[print settings](typeref:///print%20settings)** class/record  
**time** property of the **[date](typeref:///date)** class/record  
**year** property of the **[date](typeref:///date)** class/record  
# record  
**record** *\(type\)*An AppleScript record.  
# DESCRIPTION  
A *record* is an unordered collection of name-value pairs. Each value may be of any type. A literal record looks like a literal list except that each item has a name, which is separated from the corresponding value with a colon\:  
set R to \{firstname\:"John", lastname\:"Doe"\}  
There is no empty record as distinct from the empty list; the empty list \{\} is treated as the empty record for purposes of containment and concatenation. Records are passed to a few important commands, such as make, and are returned as a way of providing a table of information. AppleScript provides some operators for testing the contents of a record and for concatenating records to form a new record. A record can be mutated in place, and is one of the classes for which set and copy behave differently.  
# WHERE USED  
The **record** type is used in the following ways\:  
**with properties** parameter of the **[duplicate](commandref:///duplicate)** command/event  
**with properties** parameter of the **[make](commandref:///make)** command/event  
# rectangle  
**rectangle** *\(type\)*A list of four numbers, designating a rectangle in the plane.  
# DESCRIPTION  
There are various standards for using four numbers to designate a rectangle. The old way is to specify the x and y coordinates of the origin corner, and the x and y coordinates of the opposite corner, of the rectangle. But the origin corner might be the top left \(traditional\) or the bottom left \(newer\), and the Cocoa standard is to use the third and fourth numbers for the width and height of the rectangle.  
# WHERE USED  
The **rectangle** type is used in the following ways\:  
**bounds** property of the **[window](typeref:///window)** class/record  
# reference  
**reference** *\(type\)\[synonyms\:* **object**, **specifier***\]*A reference to an element in a collection of objects.  
# DESCRIPTION  
The *reference* \(or specifier, or object\) datatype is used in a dictionary as a wild-card type, to indicate that a value will be a reference to an element, of some unspecified class, within the application.  
# WHERE USED  
The **reference** type is used in the following ways\:  
direct parameter to the **[close](commandref:///close)** command/event  
direct parameter to the **[print](commandref:///print)** command/event  
direct parameter to the **[count](commandref:///count)** command/event  
direct parameter to the **[delete](commandref:///delete)** command/event  
result of **[duplicate](commandref:///duplicate)** command  
direct parameter to the **[duplicate](commandref:///duplicate)** command/event  
result of **[make](commandref:///make)** command  
direct parameter to the **[show](commandref:///show)** command/event  
direct parameter to the **[move](commandref:///move)** command/event  
direct parameter to the **[schedule](commandref:///schedule)** command/event  
# text  
**text** *\(type\)*A plain text string value.  
# DESCRIPTION  
The *text* or *string* datatype is the basic text string type. It is Unicode, so it can include any character. However, the *read* and *write* scripting addition commands interpret as text or as string \(or nothing\) to mean MacRoman; to get UTF-16, say as Unicode text, and to get UTF-8, say as «class utf8».  
A literal text string is delimited by quotation marks, with the empty string symbolized by "".  
set s to "howdy"  
class of s -- **text**  
The following are the **properties** of a text string. They are read-only.  
*length*  
The number of characters of the text string. You can get this same information by sending the count message to the string.  
*quoted form*  
A rendering of the text string suitable for handing to the shell as an argument to a command. The text string is wrapped in single quotation marks and internal quotation marks are escaped.  
*id*  
The codepoints of the Unicode characters constituting the text string\: an integer or list of integers. The reverse operation, from a list of integers to text, is through the string id specifier.  
The following are the **elements** of a text string. They cannot be set, because a text string cannot be mutated in place.  
*character*  
A text string representing a single character of the text string.  
*word*  
A text string representing a single word of the text string. It has no spaces or other word-boundary punctuation.  
*paragraph*  
A text string representing a single paragraph \(or line\) of the text string. It has no line breaks. AppleScript treats a return, a newline, or both together \(CRLF\) as a line break.  
*text*  
A run of text. Its purpose is to let you obtain a single continuous text string using a range element specifier\:  
words 1 thru 3 of "Now is the winter" -- **\{"Now", "is", "the"\}**  
text from word 1 to word 3 of "Now is the winter" -- **"Now is the"**  
*text item*  
A “field” of text, where the field delimiter is AppleScript’s text item delimiters property \(or, if text item delimiters is a list, any item of that list\).  
# WHERE USED  
The **text** type is used in the following ways\:  
direct parameter to the **[add contact named](commandref:///add%20contact%20named)** command/event  
direct parameter to the **[parse quicksilver input](commandref:///parse%20quicksilver%20input)** command/event  
result of **[get localized string](commandref:///get%20localized%20string)** command  
direct parameter to the **[get localized string](commandref:///get%20localized%20string)** command/event  
**current list name** property of the **[application](typeref:///application)** class/record  
**current list url** property of the **[application](typeref:///application)** class/record  
**date string** property of the **[date](typeref:///date)** class/record  
**fax number** property of the **[print settings](typeref:///print%20settings)** class/record  
**from** parameter of the **[get localized string](commandref:///get%20localized%20string)** command/event  
**id** property of the **[list](typeref:///list)** class/record  
**id** property of the **[tag](typeref:///tag)** class/record  
**id** property of the **[to do](typeref:///to%20do)** class/record  
**keyboard shortcut** property of the **[tag](typeref:///tag)** class/record  
**name** property of the **[window](typeref:///window)** class/record  
**name** property of the **[application](typeref:///application)** class/record  
**name** property of the **[list](typeref:///list)** class/record  
**name** property of the **[tag](typeref:///tag)** class/record  
**name** property of the **[to do](typeref:///to%20do)** class/record  
**name** property of the **[item details](typeref:///item%20details)** class/record  
**notes** property of the **[to do](typeref:///to%20do)** class/record  
**notes** property of the **[item details](typeref:///item%20details)** class/record  
**POSIX path** property of the **[alias](typeref:///alias)** class/record  
**POSIX path** property of the **[file](typeref:///file)** class/record  
**short date string** property of the **[date](typeref:///date)** class/record  
**tag names** property of the **[area](typeref:///area)** class/record  
**tag names** property of the **[to do](typeref:///to%20do)** class/record  
**tag names** property of the **[item details](typeref:///item%20details)** class/record  
**target printer** property of the **[print settings](typeref:///print%20settings)** class/record  
**time string** property of the **[date](typeref:///date)** class/record  
**version** property of the **[application](typeref:///application)** class/record  
# type class  
**type class** *\(type\)\[synonyms\:* **type***\]*A class value.  
# DESCRIPTION  
The *type class* datatype \(or *class*, or *type*\) is the value type of a value type. For example, when you ask AppleScript for the class of a value, and AppleScript tells you that it is an integer or a real or a folder or whatever, this value must itself be of some class, and this is it. There are times when it is necessary to pass a class to a command; for example, the make command needs to know what class of object to create.  
# WHERE USED  
The **type class** type is used in the following ways\:  
**each** parameter of the **[count](commandref:///count)** command/event  
**new** parameter of the **[make](commandref:///make)** command/event  
# STANDARD SUITE  
**Standard Suite**Common classes and commands for all applications.  
# COMMANDS  
# close  
**close** *\(verb\)*Close a window. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# COMMAND SYNTAX  
close {==*[reference](typeref:///reference)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
the window\(s\) to close.  
# CLASSES  
The following classes respond to the **close** command\:  
[window](typeref:///window)  




# count  
**count** *\(verb\)*Return the number of elements of a particular class within an object. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# FUNCTION SYNTAX  
set *theResult* to count {==*[reference](typeref:///reference)*==} ¬  
each {==*[type class](typeref:///type%20class)*==}  
# RESULT  
[integer](typeref:///integer)the number of elements  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
the object whose elements are to be counted  
each  
optional  
[type class](typeref:///type%20class)  
The class of objects to be counted.  
# delete  
**delete** *\(verb\)*Delete an object. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# COMMAND SYNTAX  
delete {==*[reference](typeref:///reference)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
the object to delete  
# duplicate  
**duplicate** *\(verb\)*Copy object\(s\) and put the copies at a new location. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# FUNCTION SYNTAX  
set *theResult* to duplicate {==*[reference](typeref:///reference)*==} ¬  
to {==*[location specifier](typeref:///location%20specifier)*==} ¬  
with properties {==*[record](typeref:///record)*==}  
# RESULT  
[reference](typeref:///reference)the duplicated object\(s\)  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
the object\(s\) to duplicate  
to  
optional  
[location specifier](typeref:///location%20specifier)  
The location for the new object\(s\).  
with properties  
optional  
[record](typeref:///record)  
Properties to be set in the new duplicated object\(s\).  
# exists  
**exists** *\(verb\)*Verify if an object exists. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# FUNCTION SYNTAX  
set *theResult* to exists {==*[any](typeref:///any)*==}  
# RESULT  
[boolean](typeref:///boolean)true if it exists, false if not  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[any](typeref:///any)  
the object in question  
# make  
**make** *\(verb\)*Make a new object. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# FUNCTION SYNTAX  
set *theResult* to make new {==*[type class](typeref:///type%20class)*==} ¬  
at {==*[location specifier](typeref:///location%20specifier)*==} ¬  
with properties {==*[record](typeref:///record)*==}  
# RESULT  
[reference](typeref:///reference)to the new object  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
at  
optional  
[location specifier](typeref:///location%20specifier)  
The location at which to insert the object.  
new  
required  
[type class](typeref:///type%20class)  
The class of the new object.  
with properties  
optional  
[record](typeref:///record)  
The initial values for properties of the object.  
# print  
**print** *\(verb\)*Print a document. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# COMMAND SYNTAX  
print {==list of *[file](typeref:///file)* or *[reference](typeref:///reference)*==} ¬  
with properties {==*[print settings](typeref:///print%20settings)*==} ¬  
print dialog {==*[boolean](typeref:///boolean)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
list of [file](typeref:///file) or [reference](typeref:///reference)  
The file\(s\), document\(s\), or window\(s\) to be printed.  
print dialog  
optional  
[boolean](typeref:///boolean)  
Should the application show the print dialog?  
with properties  
optional  
[print settings](typeref:///print%20settings)  
The print settings to use.  
# CLASSES  
The following classes respond to the **print** command\:  
[window](typeref:///window)  
[application](typeref:///application)  



# quit  
**quit** *\(verb\)*Quit the application. \(from [Standard Suite](suiteref:///Standard%20Suite)\)  
# COMMAND SYNTAX  
quit   
# CLASSES  
The following classes respond to the **quit** command\:  
[application](typeref:///application)  




# CLASSES  
# window  
**window** *\(noun\)*A window.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
bounds  
get/set  
[rectangle](typeref:///rectangle)  
The bounding rectangle of the window.  
closeable  
get  
[boolean](typeref:///boolean)  
Whether the window has a close box.  
id  
get  
[integer](typeref:///integer)  
The unique identifier of the window.  
index  
get/set  
[integer](typeref:///integer)  
The index of the window, ordered front to back.  
minimizable  
get  
[boolean](typeref:///boolean)  
Whether the window can be minimized.  
minimized  
get/set  
[boolean](typeref:///boolean)  
Whether the window is currently minimized.  
name  
get  
[text](typeref:///text)  
The full title of the window.  
resizable  
get  
[boolean](typeref:///boolean)  
Whether the window can be resized.  
visible  
get/set  
[boolean](typeref:///boolean)  
Whether the window is currently visible.  
zoomable  
get  
[boolean](typeref:///boolean)  
Whether the window can be zoomed.  
zoomed  
get/set  
[boolean](typeref:///boolean)  
Whether the window is currently zoomed.  
# COMMANDS  
The **window** class responds to the following commands\:  
# Command  
# Description  
[close](commandref:///close)  
Close a window.  
[print](commandref:///print)  
Print a document.  
[save](commandref:///save)  

# WHERE USED  
The **window** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
# ENUMERATIONS  
# printing error handling  
**printing error handling** *\(enumeration\)*  
# CONSTANTS  
# Constant  
# Description  
detailed  
print a detailed report of PostScript errors  
standard  
Standard PostScript error handling  
# WHERE USED  
The **printing error handling** enumeration is used in the following ways\:  
**error handling** property of the **[print settings](typeref:///print%20settings)** class/record  
# RECORDS  
# print settings  
**print settings** *\(record\)*  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
collating  
get/set  
[boolean](typeref:///boolean)  
Should printed copies be collated?  
copies  
get/set  
[integer](typeref:///integer)  
the number of copies of a document to be printed  
ending page  
get/set  
[integer](typeref:///integer)  
the last page of the document to be printed  
error handling  
get/set  
[printing error handling](typeref:///printing%20error%20handling)  
how errors are handled  
fax number  
get/set  
[text](typeref:///text)  
for fax number  
pages across  
get/set  
[integer](typeref:///integer)  
number of logical pages laid across a physical page  
pages down  
get/set  
[integer](typeref:///integer)  
number of logical pages laid out down a physical page  
starting page  
get/set  
[integer](typeref:///integer)  
the first page of the document to be printed  
target printer  
get/set  
[text](typeref:///text)  
for target printer  
# WHERE USED  
The **print settings** record is used in the following ways\:  
**with properties** parameter of the **[print](commandref:///print)** command/event  
# THINGS SUITE  
**Things Suite**Things specific classes and commands.  
# COMMANDS  
# add contact named  
**add contact named** *\(verb\)*Add a contact to Things \(from [Things Suite](suiteref:///Things%20Suite)\)  
# FUNCTION SYNTAX  
set *theResult* to add contact named {==*[text](typeref:///text)*==}  
# RESULT  
[contact](typeref:///contact)New contact  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[text](typeref:///text)  
Name of the contact  
# edit  
**edit** *\(verb\)*Edit Things to do \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
edit {==*[to do](typeref:///to%20do)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[to do](typeref:///to%20do)  
To do to edit  
# CLASSES  
The following classes respond to the **edit** command\:  
[project](typeref:///project)  
[to do](typeref:///to%20do)  
[selected to do](typeref:///selected%20to%20do)  


# empty trash  
**empty trash** *\(verb\)*Empty Things trash \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
empty trash   
# log completed now  
**log completed now** *\(verb\)*Log completed items now \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
log completed now   
# move  
**move** *\(verb\)*Move a to do to a different list. \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
move {==*[reference](typeref:///reference)*==} ¬  
to {==*[list](typeref:///list)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
the to do\(s\) to move  
to  
required  
[list](typeref:///list)  
List to use as target  
# CLASSES  
The following classes respond to the **move** command\:  
[project](typeref:///project)  
[to do](typeref:///to%20do)  
[selected to do](typeref:///selected%20to%20do)  


# parse quicksilver input  
**parse quicksilver input** *\(verb\)*Add new Things to do from input in Quicksilver syntax \(from [Things Suite](suiteref:///Things%20Suite)\)  
# FUNCTION SYNTAX  
set *theResult* to parse quicksilver input {==*[text](typeref:///text)*==}  
# RESULT  
[to do](typeref:///to%20do)New to do  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[text](typeref:///text)  
To do description  
# schedule  
**schedule** *\(verb\)*Schedules a Things to do \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
schedule {==*[reference](typeref:///reference)*==} ¬  
for {==*[date](typeref:///date)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
To do to schedule  
for  
required  
[date](typeref:///date)  
Date to schedule a to do for.  
# CLASSES  
The following classes respond to the **schedule** command\:  
[project](typeref:///project)  
[to do](typeref:///to%20do)  
[selected to do](typeref:///selected%20to%20do)  


# show  
**show** *\(verb\)*Show Things item in the UI \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
show {==*[reference](typeref:///reference)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
*direct parameter*  
required  
[reference](typeref:///reference)  
Item to show  
# CLASSES  
The following classes respond to the **show** command\:  
[area](typeref:///area)  
[contact](typeref:///contact)  
[to do](typeref:///to%20do)  


[list](typeref:///list)  
[project](typeref:///project)  
[selected to do](typeref:///selected%20to%20do)  


# show quick entry panel  
**show quick entry panel** *\(verb\)*Show Things Quick Entry panel \(from [Things Suite](suiteref:///Things%20Suite)\)  
# COMMAND SYNTAX  
show quick entry panel with autofill {==*[boolean](typeref:///boolean)*==} ¬  
with properties {==*[item details](typeref:///item%20details)*==}  
# PARAMETERS  
# Parameter  
# Required  
# Type  
# Description  
with autofill  
optional  
[boolean](typeref:///boolean)  
Invoke autofill feature before showing the panel  
with properties  
optional  
[item details](typeref:///item%20details)  
Properties for new to do. Ignored if using autofill.  
# CLASSES  
# application  
**application** *\(noun\)*The application's top-level scripting object.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
frontmost  
get  
[boolean](typeref:///boolean)  
Is this the frontmost \(active\) application?  
name  
get  
[text](typeref:///text)  
The name of the application.  
version  
get  
[text](typeref:///text)  
The version of the application.  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[area](typeref:///area)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[contact](typeref:///contact)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[list](typeref:///list)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[project](typeref:///project)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[selected to do](typeref:///selected%20to%20do)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[tag](typeref:///tag)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[to do](typeref:///to%20do)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[window](typeref:///window)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

# COMMANDS  
The **application** class responds to the following commands\:  
# Command  
# Description  
[open](commandref:///open)  

[print](commandref:///print)  
Print a document.  
[quit](commandref:///quit)  
Quit the application.  
# area  
**area** *\(noun\), pl* **areas**Represents a Things area of responsibility.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
collapsed  
get/set  
[boolean](typeref:///boolean)  
Is this area collapsed?  
id  
get  
[text](typeref:///text)  
The unique identifier of the list.  
[list](typeref:///list)  
name  
get/set  
[text](typeref:///text)  
Name of the list  
[list](typeref:///list)  
tag names  
get/set  
[text](typeref:///text)  
Tag names separated by comma  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[tag](typeref:///tag)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[to do](typeref:///to%20do)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[list](typeref:///list)  
# COMMANDS  
The **area** class responds to the following commands\:  
# Command  
# Description  
[show](commandref:///show)  
Show Things item in the UI [list](typeref:///list)  
# SUPERCLASS  
The **area** class inherits elements and properties from [list](typeref:///list).  
# WHERE USED  
The **area** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
**area** property of the **[to do](typeref:///to%20do)** class/record  
# contact  
**contact** *\(noun\), pl* **contacts**Represents a Things contact.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
id  
get  
[text](typeref:///text)  
The unique identifier of the list.  
[list](typeref:///list)  
name  
get/set  
[text](typeref:///text)  
Name of the list  
[list](typeref:///list)  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[to do](typeref:///to%20do)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[list](typeref:///list)  
# COMMANDS  
The **contact** class responds to the following commands\:  
# Command  
# Description  
[show](commandref:///show)  
Show Things item in the UI [list](typeref:///list)  
# SUPERCLASS  
The **contact** class inherits elements and properties from [list](typeref:///list).  
# WHERE USED  
The **contact** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
result of **[add contact named](commandref:///add%20contact%20named)** command  
**contact** property of the **[to do](typeref:///to%20do)** class/record  
# list  
**list** *\(noun\), pl* **lists**Represents a Things list.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
id  
get  
[text](typeref:///text)  
The unique identifier of the list.  
name  
get/set  
[text](typeref:///text)  
Name of the list  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[to do](typeref:///to%20do)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

# COMMANDS  
The **list** class responds to the following commands\:  
# Command  
# Description  
[show](commandref:///show)  
Show Things item in the UI  
# SUBCLASSES  
The [area](typeref:///area) and [contact](typeref:///contact) classes inherit the elements and properties of the **list** class.  
# WHERE USED  
The **list** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
**to** parameter of the **[move](commandref:///move)** command/event  
# project  
**project** *\(noun\), pl* **projects**Represents a Things project.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
activation date  
get  
[date](typeref:///date)  
Activation date of the scheduled to do  
[to do](typeref:///to%20do)  
area  
get/set  
[area](typeref:///area)  
Area the to do belongs to  
[to do](typeref:///to%20do)  
cancellation date  
get/set  
[date](typeref:///date)  
Cancellation date of the to do  
[to do](typeref:///to%20do)  
completion date  
get/set  
[date](typeref:///date)  
Completion date of the to do  
[to do](typeref:///to%20do)  
contact  
get/set  
[contact](typeref:///contact)  
Contact the to do is assigned to  
[to do](typeref:///to%20do)  
creation date  
get/set  
[date](typeref:///date)  
Creation date of the to do  
[to do](typeref:///to%20do)  
due date  
get/set  
[date](typeref:///date)  
Due date of the to do  
[to do](typeref:///to%20do)  
id  
get  
[text](typeref:///text)  
The unique identifier of the to do.  
[to do](typeref:///to%20do)  
modification date  
get/set  
[date](typeref:///date)  
Modification date of the to do  
[to do](typeref:///to%20do)  
name  
get/set  
[text](typeref:///text)  
Name of the to do  
[to do](typeref:///to%20do)  
notes  
get/set  
[text](typeref:///text)  
Notes of the to do  
[to do](typeref:///to%20do)  
project  
get/set  
[project](typeref:///project)  
Project the to do belongs to  
[to do](typeref:///to%20do)  
status  
get/set  
[status](typeref:///status)  
Status of the to do  
[to do](typeref:///to%20do)  
tag names  
get/set  
[text](typeref:///text)  
Tag names separated by comma  
[to do](typeref:///to%20do)  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[tag](typeref:///tag)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[to do](typeref:///to%20do)  
[to do](typeref:///to%20do)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

# COMMANDS  
The **project** class responds to the following commands\:  
# Command  
# Description  
[edit](commandref:///edit)  
Edit Things to do [to do](typeref:///to%20do)  
[move](commandref:///move)  
Move a to do to a different list. [to do](typeref:///to%20do)  
[schedule](commandref:///schedule)  
Schedules a Things to do [to do](typeref:///to%20do)  
[show](commandref:///show)  
Show Things item in the UI [to do](typeref:///to%20do)  
# SUPERCLASS  
The **project** class inherits elements and properties from [to do](typeref:///to%20do).  
# WHERE USED  
The **project** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
**project** property of the **[to do](typeref:///to%20do)** class/record  
# selected to do  
**selected to do** *\(noun\), pl* **selected to dos**Represents a to do selected in Things UI.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
activation date  
get  
[date](typeref:///date)  
Activation date of the scheduled to do  
[to do](typeref:///to%20do)  
area  
get/set  
[area](typeref:///area)  
Area the to do belongs to  
[to do](typeref:///to%20do)  
cancellation date  
get/set  
[date](typeref:///date)  
Cancellation date of the to do  
[to do](typeref:///to%20do)  
completion date  
get/set  
[date](typeref:///date)  
Completion date of the to do  
[to do](typeref:///to%20do)  
contact  
get/set  
[contact](typeref:///contact)  
Contact the to do is assigned to  
[to do](typeref:///to%20do)  
creation date  
get/set  
[date](typeref:///date)  
Creation date of the to do  
[to do](typeref:///to%20do)  
due date  
get/set  
[date](typeref:///date)  
Due date of the to do  
[to do](typeref:///to%20do)  
id  
get  
[text](typeref:///text)  
The unique identifier of the to do.  
[to do](typeref:///to%20do)  
modification date  
get/set  
[date](typeref:///date)  
Modification date of the to do  
[to do](typeref:///to%20do)  
name  
get/set  
[text](typeref:///text)  
Name of the to do  
[to do](typeref:///to%20do)  
notes  
get/set  
[text](typeref:///text)  
Notes of the to do  
[to do](typeref:///to%20do)  
project  
get/set  
[project](typeref:///project)  
Project the to do belongs to  
[to do](typeref:///to%20do)  
status  
get/set  
[status](typeref:///status)  
Status of the to do  
[to do](typeref:///to%20do)  
tag names  
get/set  
[text](typeref:///text)  
Tag names separated by comma  
[to do](typeref:///to%20do)  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[tag](typeref:///tag)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[to do](typeref:///to%20do)  
# COMMANDS  
The **selected to do** class responds to the following commands\:  
# Command  
# Description  
[edit](commandref:///edit)  
Edit Things to do [to do](typeref:///to%20do)  
[move](commandref:///move)  
Move a to do to a different list. [to do](typeref:///to%20do)  
[schedule](commandref:///schedule)  
Schedules a Things to do [to do](typeref:///to%20do)  
[show](commandref:///show)  
Show Things item in the UI [to do](typeref:///to%20do)  
# SUPERCLASS  
The **selected to do** class inherits elements and properties from [to do](typeref:///to%20do).  
# WHERE USED  
The **selected to do** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
# tag  
**tag** *\(noun\), pl* **tags**Represents a Things tag.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
id  
get  
[text](typeref:///text)  
The unique identifier of the tag.  
keyboard shortcut  
get/set  
[text](typeref:///text)  
Keyboard shortcut for the tag  
name  
get/set  
[text](typeref:///text)  
Name of the tag  
parent tag  
get/set  
[tag](typeref:///tag)  
Parent tag  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[tag](typeref:///tag)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

[to do](typeref:///to%20do)  
get  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

# WHERE USED  
The **tag** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
element of **[area](typeref:///area)** class  
element of **[project](typeref:///project)** class  
element of **[to do](typeref:///to%20do)** class  
element of **[selected to do](typeref:///selected%20to%20do)** class  
**parent tag** property of the **[tag](typeref:///tag)** class/record  
# to do  
**to do** *\(noun\), pl* **to dos**Represents a Things to do.  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
activation date  
get  
[date](typeref:///date)  
Activation date of the scheduled to do  
area  
get/set  
[area](typeref:///area)  
Area the to do belongs to  
cancellation date  
get/set  
[date](typeref:///date)  
Cancellation date of the to do  
completion date  
get/set  
[date](typeref:///date)  
Completion date of the to do  
contact  
get/set  
[contact](typeref:///contact)  
Contact the to do is assigned to  
creation date  
get/set  
[date](typeref:///date)  
Creation date of the to do  
due date  
get/set  
[date](typeref:///date)  
Due date of the to do  
id  
get  
[text](typeref:///text)  
The unique identifier of the to do.  
modification date  
get/set  
[date](typeref:///date)  
Modification date of the to do  
name  
get/set  
[text](typeref:///text)  
Name of the to do  
notes  
get/set  
[text](typeref:///text)  
Notes of the to do  
project  
get/set  
[project](typeref:///project)  
Project the to do belongs to  
status  
get/set  
[status](typeref:///status)  
Status of the to do  
tag names  
get/set  
[text](typeref:///text)  
Tag names separated by comma  
# ELEMENTS  
# Element  
# Access  
# Key Forms  
# Description  
[tag](typeref:///tag)  
get/ make/ delete  
by name  
by index  
by range  
relative to others  
by whose/where  
by unique ID  

# COMMANDS  
The **to do** class responds to the following commands\:  
# Command  
# Description  
[edit](commandref:///edit)  
Edit Things to do  
[move](commandref:///move)  
Move a to do to a different list.  
[schedule](commandref:///schedule)  
Schedules a Things to do  
[show](commandref:///show)  
Show Things item in the UI  
# SUBCLASSES  
The [project](typeref:///project) and [selected to do](typeref:///selected%20to%20do) classes inherit the elements and properties of the **to do** class.  
# WHERE USED  
The **to do** class is used in the following ways\:  
element of **[application](typeref:///application)** class  
element of **[area](typeref:///area)** class  
element of **[list](typeref:///list)** class  
element of **[contact](typeref:///contact)** class  
element of **[project](typeref:///project)** class  
element of **[tag](typeref:///tag)** class  
direct parameter to the **[edit](commandref:///edit)** command/event  
result of **[parse quicksilver input](commandref:///parse%20quicksilver%20input)** command  
# ENUMERATIONS  
# status  
**status** *\(enumeration\)*  
# CONSTANTS  
# Constant  
# Description  
canceled  
To do has been canceled.  
completed  
To do has been completed.  
open  
To do is open.  
# WHERE USED  
The **status** enumeration is used in the following ways\:  
**status** property of the **[to do](typeref:///to%20do)** class/record  
# RECORDS  
# item details  
**item details** *\(record\)*  
# PROPERTIES  
# Property  
# Access  
# Type  
# Description  
due date  
get/set  
[date](typeref:///date)  
Due date  
name  
get/set  
[text](typeref:///text)  
Name  
notes  
get/set  
[text](typeref:///text)  
Notes  
tag names  
get/set  
[text](typeref:///text)  
Tag names  
# WHERE USED  
The **item details** record is used in the following ways\:  
**with properties** parameter of the **[show quick entry panel](commandref:///show%20quick%20entry%20panel)** command/event  

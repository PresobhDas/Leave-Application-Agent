from pydantic import BaseModel, Field
from typing import Literal, Optional, List, TypedDict, Annotated
from langchain_core.messages import BaseMessage
from operator import add

class WeatherData(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    windspeed: float
    winddirection: float

class WeatherDataResponse(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    weatherData : WeatherData | None = None

class EmployeeMaster(BaseModel):
    employeeId:str
    name:str
    department:str
    location:str
    DOB:int
    isActive:bool
    email:str
    ssn:str
class EmployeeMasterResponseModel(BaseModel):
    dataFound: Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    employee: EmployeeMaster | None = None

class EmployeeLeaveData(BaseModel):
    employeeId:str
    department:str
    leaveType:str
    startDate:str
    endDate:str
    numberOfDays:int

class EmployeeLeaveResponseModel(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    employeeLeave : EmployeeLeaveData | None = None

class RagData(BaseModel):
    score:Optional[float] = 0.0
    text:Optional[str] = ''
    title:Optional[str] = ''
    docName:Optional[str] = ''
class RagDataResponseModel(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    results : List[RagData] = Field(default_factory=list)
    formattedContext : str | None = None

class InputDetails(BaseModel):
    inp_query:str
    user_id: str

class UploadRequest(BaseModel):
    filename: str

class RagasInp(BaseModel):
    inpQuestion : str
    retrievedContext : List[str]
    llmResponse : str
    confidenceScore : List[float] = Field(default_factory=lambda: [1.0])

class RagasMetrics(BaseModel):
    faithfulness : float = Field(default=0.0)
    relevancy : float  = Field(default=0.0)

class RagasData(BaseModel):
    ragasInp : RagasInp
    ragasMetrics : RagasMetrics

class RagState(TypedDict):
    userId : str
    question:str
    sub_questions: List[str]          # 👈 new
    sub_answers: List[str] 
    current_sub_question: Optional[str]
    messages: List[BaseMessage]
    context:List[str]
    formatted_contexts: List[str]
    llmResponse:str
    confidenceScore : List[float]
    tool_execution_count: int
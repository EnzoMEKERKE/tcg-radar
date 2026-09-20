from dataclasses import dataclass
@dataclass
class Connector:
    id:str; name:str; country:str; base_url:str; mode:str='html'
    async def search(self, query:str): raise NotImplementedError

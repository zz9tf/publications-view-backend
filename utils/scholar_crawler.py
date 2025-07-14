from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
from datetime import datetime
import logging
import asyncio
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class GoogleScholarCrawler:
    """
    🔍 Google Scholar 论文爬虫
    功能：从Google Scholar页面抓取论文详细信息
    """
    
    def __init__(self, headless=False):
        """
        初始化爬虫配置
        
        Args:
            headless (bool): 是否使用无头浏览器模式
        """
        self.options = Options()
        if headless:
            self.options.add_argument("--headless")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--window-size=1200,800")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        
        self.driver = None
        self.wait = None
        self.google_scholar_search_dict = {}
        self._initialize_driver()
        
    def _initialize_driver(self):
        """初始化WebDriver"""
        if self.driver is None:
            try:
                self.driver = webdriver.Chrome(options=self.options)
                self.wait = WebDriverWait(self.driver, 10)
                logger.info("WebDriver已初始化")
            except Exception as e:
                logger.error(f"WebDriver初始化失败: {str(e)}")
                raise e
            
    def init_basic_scholar_info(self, google_scholar_url: str, client_id: str, search_id: str):
        if client_id not in self.google_scholar_search_dict:
            self.google_scholar_search_dict[client_id] = {}
        
        self.google_scholar_search_dict[client_id][search_id] = {
            "client_id": client_id,
            "search_id": search_id,
            "url": google_scholar_url,
            "author_name": "",
            "status": "processing",
            "progress": 0,
            "fetched_paper_count": 0,
            "total_paper_count": 0,
            "papers_elements": None,
            "papers": []
        }
        
        logger.info(f"开始搜索: {google_scholar_url}")
        self.driver.get(google_scholar_url)
        time.sleep(2)  # 等待页面加载
        
        # 获取作者信息
        author_info = self.driver.find_element(By.CSS_SELECTOR, ".gs_ai_pho")
        author_name = author_info.text.strip()
        logger.info(f"作者信息: {author_name}")
        self.google_scholar_search_dict[search_id]["author_name"] = author_name

        # 获取搜索结果
        paper_elements = self.driver.find_elements(By.CSS_SELECTOR, ".gs_r.gs_or.gs_scl")
        self.google_scholar_search_dict[search_id]["total_paper_count"] = len(paper_elements)
        self.google_scholar_search_dict[search_id]["papers_elements"] = paper_elements

    def search_papers(self, client_id: str, search_id: str) -> List[Dict[str, Any]]:
        """
        搜索论文
        
        Args:
            google_scholar_url (str): Google Scholar URL
            client_id (str): 客户端ID
        Returns:
            List[Dict[str, Any]]: 论文列表
        """
        try:
            search_info = self.google_scholar_search_dict[client_id][search_id]
            papers = []
            paper_elements = search_info["papers_elements"]
            
            for i, elem in enumerate(paper_elements):
                try:
                    # 提取标题和链接
                    title_elem = elem.find_element(By.CSS_SELECTOR, ".gs_rt a")
                    title = title_elem.text.strip()
                    link = title_elem.get_attribute("href")
                    
                    if not title:
                        continue
                    
                    # 提取作者、发表信息
                    authors_venue_elem = elem.find_element(By.CSS_SELECTOR, ".gs_a")
                    authors_venue_text = authors_venue_elem.text.strip()
                    print(authors_venue_text)
                    
                    # 提取作者
                    authors_match = re.search(r'^(.*?)-', authors_venue_text)
                    authors = []
                    if authors_match:
                        authors_text = authors_match.group(1).strip()
                        authors = [author.strip() for author in re.split(r',|\u2026', authors_text) if author.strip()]
                        print(authors)
                    
                    # 提取年份、月份、日期
                    year = None
                    month = 1
                    day = 1
                    
                    # 首先尝试提取完整日期 (YYYY/MM/DD 或 YYYY-MM-DD)
                    date_match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', authors_venue_text)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                    else:
                        # 尝试提取年月 (YYYY/MM 或 YYYY-MM)
                        date_match = re.search(r'(\d{4})[/-](\d{1,2})', authors_venue_text)
                        if date_match:
                            year = int(date_match.group(1))
                            month = int(date_match.group(2))
                        else:
                            # 只提取年份
                            year_match = re.search(r'\b(19|20)\d{2}\b', authors_venue_text)
                            if year_match:
                                year = int(year_match.group())
                            
                            # 尝试提取月份
                            month_names = {
                                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                            }
                            for month_name, month_num in month_names.items():
                                if month_name in authors_venue_text.lower():
                                    month = month_num
                                    # 尝试提取日期（数字+月份附近）
                                    day_match = re.search(r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*' + month_name, authors_venue_text.lower())
                                    if day_match:
                                        day = int(day_match.group(1))
                                    break
                    
                    print(f"Year: {year}, Month: {month}, Day: {day}")
                    
                    # 格式化日期
                    date_str = f"{year}-{month:02d}-{day:02d}" if year else None
                    
                    # 提取venue
                    venue_match = re.search(r'-\s+(.*?)(?:,|\d{4}|$)', authors_venue_text)
                    venue = venue_match.group(1).strip() if venue_match else None
                    print(venue)
                    
                    # 提取引用次数
                    citations = 0
                    try:
                        cited_elem = elem.find_element(By.CSS_SELECTOR, ".gs_fl a")
                        cited_text = cited_elem.text
                        citations_match = re.search(r'Cited by (\d+)', cited_text)
                        if citations_match:
                            citations = int(citations_match.group(1))
                    except:
                        pass
                    print(citations)
                    
                    # 提取摘要
                    description = ""
                    try:
                        description_elem = elem.find_element(By.CSS_SELECTOR, ".gs_rs")
                        description = description_elem.text.strip()
                    except:
                        pass
                    print(description)
                    
                    # 确定类型
                    paper_type = "Research Paper"
                    if venue:
                        if any(conf_word in venue.lower() for conf_word in ['conference', 'workshop', 'symposium', 'proceedings']):
                            paper_type = "Conference"
                        elif any(journal_word in venue.lower() for journal_word in ['journal', 'transactions', 'letters']):
                            paper_type = "Journal"
                        elif 'arxiv' in venue.lower():
                            paper_type = "Preprint"
                    print(paper_type)
                    
                    paper_info = {
                        "id": f"paper-{i+1}",
                        "title": title,
                        "authors": authors,
                        "year": year if year else datetime.now().year,
                        "date": date_str if date_str else f"{datetime.now().year}-01-01",
                        "citations": citations,
                        "publisher": venue,
                        "paper_type": paper_type,
                        "description": description,
                        "link": link
                    }
                    
                    logger.info(f"paper_info: {paper_info}")
                    input()
                    
                    # papers.append(paper_info)
                    # logger.info(f"提取论文: {title[:50]}...")
                    
                except Exception as e:
                    logger.error(f"提取论文信息时出错: {str(e)}")
                    continue
            
            logger.info(f"搜索完成，找到 {len(papers)} 篇论文")
            self.google_scholar_search_dict[client_id][search_id]["papers"] = papers
            
        except Exception as e:
            logger.error(f"搜索论文时出错: {str(e)}")
            self.google_scholar_search_dict[client_id][search_id]["status"] = "error"
        finally:
            self.close()
    
    def close(self):
        """
        🔒 关闭浏览器
        """
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.wait = None
            logger.info("浏览器已关闭")

# 创建单例实例
scholar_crawler = GoogleScholarCrawler(headless=True) 